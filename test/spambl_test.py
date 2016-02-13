#!/usr/bin/python
# -*- coding: utf-8 -*-

import unittest
from spambl import (UnknownCodeError, NXDOMAIN, HpHosts, 
                    IpDNSBL, DomainDNSBL, GeneralDNSBL,
                    GoogleSafeBrowsing, UnathorizedAPIKeyError, HostCollection,
                     CodeClassificationMap, SumClassificationMap, Hostname, IpAddress, 
                     host, is_valid_url, BaseUrlTester, RedirectUrlResolver,
    AddressListItem)
from mock import Mock, patch, MagicMock
from itertools import combinations, product, chain

from requests.exceptions import HTTPError, InvalidSchema, InvalidURL,\
    ConnectionError, Timeout
from dns import name, reversename

from nose_parameterized import parameterized

class BaseDNSBLTest(object):
    
    valid_hosts = ()
    invalid_hosts = ()
    factory = None
    
    @classmethod
    def setUpClass(cls):
        
        cls.query_domain_str = 'test.query.domain'
        cls.query_domain = name.from_text(cls.query_domain_str)
    
    def setUp(self):
        
        self.classification_map = MagicMock()
        
        self.dnsbl_service = self.factory('test_service', self.query_domain_str, self.classification_map)
        
        dns_answer_mock = Mock()
        self.dns_answer_string = dns_answer_mock.to_text.return_value = '121.0.0.1'
        
        self.patcher = patch('spambl.query')
        self.dns_query_mock = self.patcher.start()
        self.dns_query_mock.return_value = [dns_answer_mock]
    
    def doTestCallForInvalidArgs(self, function):
        ''' Perform test of a function that should raise ValueError for given data '''
        
        for h in self.invalid_hosts:
            self.assertRaises(ValueError, function, h)
        
    def testContainsForInvalidArgs(self):
        ''' The call should raise ValueError '''
        
        self.doTestCallForInvalidArgs(self.dnsbl_service.__contains__)
        
    def testLookupForInvalidArgs(self):
        ''' The call should raise ValueError '''
        
        self.doTestCallForInvalidArgs(self.dnsbl_service.lookup)
            
    def testContainsForListedValues(self):
        ''' __contains__ should return  true '''

        for h in self.valid_hosts:
            self.assertTrue(h in self.dnsbl_service)
        
    def testContainsForNotListedValues(self):
        ''' __contains__ should return  true '''
        
        self.dns_query_mock.side_effect = NXDOMAIN('Test NXDOMAIN')
        
        for h in self.valid_hosts:
            self.assertFalse(h in self.dnsbl_service)
            
    def testLookupForListedValues(self):
        ''' lookup method must return object with value equal to
        ip strings it was passed '''
        
        for h in self.valid_hosts:
            actual = self.dnsbl_service.lookup(h)
            self.assertEqual(actual.value, h)
            
    def testLookupForNotListedValues(self):
        ''' lookup method must return None  '''
        
        self.dns_query_mock.side_effect = NXDOMAIN('Test NXDOMAIN')
        
        for h in self.valid_hosts:
            actual = self.dnsbl_service.lookup(h)
            self.assertIsNone(actual)
            
    def testLookupForListedWithUnknownCodes(self,):
        ''' lookup method must raise UnknownCodeError '''
        
        self.classification_map.__getitem__.side_effect = UnknownCodeError('Unknown code error')
        
        for h in self.valid_hosts:
            self.assertRaises(UnknownCodeError, self.dnsbl_service.lookup, h)
        
    def tearDown(self):
        
        self.patcher.stop()
            
class IpDNSBLTest(BaseDNSBLTest, unittest.TestCase):
    
    valid_hosts = u'255.0.120.1', u'2001:db8:abc:123::42'
    invalid_hosts = u't1.pl', u't2.com'
    factory = IpDNSBL
        
class DomainDNSBLTest(BaseDNSBLTest, unittest.TestCase):
    
    valid_hosts = u't1.pl', u't2.com'
    invalid_hosts = u'255.0.120.1', u'2001:db8:abc:123::42', '-aaa'
    factory = DomainDNSBL
            
class GeneralDNSBLTest(BaseDNSBLTest, unittest.TestCase):
    
    valid_hosts = u't1.pl', u'255.0.120.1', u'2001:db8:abc:123::42'
    invalid_hosts = u'266.0.120.1', '/e'
    factory = GeneralDNSBL
    
class CodeClassificationMapTest(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.code_item_class = {1: 'Class #1', 2: 'Class #2'}
        cls.invalid_keys = 3, 4
        
        cls.map = CodeClassificationMap(cls.code_item_class)
        
        
    def testGetItemForValidKeys(self):
        ''' For a listed key, __getitem__ should return expected classification '''
        
        for key in self.code_item_class:
            self.assertEqual(self.map[key], self.code_item_class[key])
            
    def testGetItemForInvalidKeys(self):
        ''' For a not listed key, __getitem__ should raise an UnknownCodeError '''
            
        for key in self.invalid_keys:
            self.assertRaises(UnknownCodeError, self.map.__getitem__, key)
            
class SumClassificationMapTest(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        
        cls.code_item_class = {2: 'Class #1', 4: 'Class #2'}
    
        cls.invalid_keys = 8, 16, 17, 21
        
        cls.map = SumClassificationMap(cls.code_item_class)
            
            
    def testGetItemForASimpleValidKey(self):
        ''' For a simple listed key, __getitem__ should return an expected classification'''
        for key in self.code_item_class:
            self.assertEqual(self.map[key], tuple([self.code_item_class[key]]))
            
    def testGetItemForAnInvalidKey(self):
        ''' For a non-listed key, __getitem__ should raise UnknownCodeError '''
        for key in self.invalid_keys:
            self.assertRaises(UnknownCodeError, self.map.__getitem__, key)
    
    def testGetItemForASumOfValidKeys(self):
        ''' For a sum of valid keys, __getitem__ should return a tuple of expected classifications '''
        for key_1, key_2 in combinations(self.code_item_class.keys(), 2):
            
            expected  = tuple([x for n, x in self.code_item_class.iteritems() if n in (key_1, key_2)])
            self.assertEqual(self.map[key_1+key_2], expected)
        
    def testGetItemForASumWithAnInvalidKey(self):
        ''' For a sum of keys, including at least one invalid, __getitem__ should
        raise UnknownCodeError
        '''
        for key_1, key_2 in product(self.code_item_class.keys(), self.invalid_keys):
            
            self.assertRaises(UnknownCodeError, self.map.__getitem__, key_1+key_2)
            
class HpHostsTest(unittest.TestCase):
    ''' Tests HpHosts methods '''
    
    @classmethod
    def setUpClass(cls):
        cls.valid_hosts = 't1.pl', u'255.255.0.1'
        cls.invalid_hosts = u'266.266.266.266', u'-test.host.pl'
        
        cls.hp_hosts = HpHosts('spambl_test_suite')
        
    def setUp(self):
        
        self.response = Mock()
        
        self.patcher = patch('spambl.get')
        self.get_mock = self.patcher.start()
        self.get_mock.return_value = self.response
    
    def testContainsForListedHosts(self):
        ''' For listed hosts, __contains__ should return True'''
        
        self.response.content = 'Listed, [TEST CLASS]'
        
        for host in self.valid_hosts:
            self.assertTrue(host in self.hp_hosts)
            
    def testContainsForNotListedHosts(self):
        ''' For not listed hosts, __contains__ should return False '''
        
        self.response.content = 'Not listed'
        
        for host in self.valid_hosts:
            self.assertFalse(host in self.hp_hosts)
            
    def testContainsForInvalidHosts(self):
        ''' For invalid hosts, __contains__ should raise a ValueError '''
        
        for val in self.invalid_hosts:
            self.assertRaises(ValueError, self.hp_hosts.__contains__, val)
                
    def testLookupForListedHosts(self):
        ''' For listed hosts, lookup should return an object representing it'''
        
        self.response.content = 'Listed, [TEST CLASS]'
        
        for host in self.valid_hosts:
            self.assertEqual(self.hp_hosts.lookup(host).value, host)
            
    def testLookupForNotListedHosts(self):
        ''' For not listed hosts, lookup should return None '''
        
        self.response.content = 'Not listed'
        
        for host in self.valid_hosts:
            self.assertEqual(self.hp_hosts.lookup(host), None)
            
    def testLookupForInvalidHosts(self):
        ''' For invalid hosts, lookup should raise a ValueError '''
        
        for val in self.invalid_hosts:
            self.assertRaises(ValueError, self.hp_hosts.lookup, val)
            
    def tearDown(self):
        self.patcher.stop()

class GoogleSafeBrowsingTest(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        
        cls.valid_urls = 'http://test.domain1.com', 'https://255.255.0.1', 
        'http://[2001:DB8:abc:123::42]', 'ftp://test.domain2.com'
        
        cls.google_safe_browsing = GoogleSafeBrowsing('test_client', '0.1', 'test_key')
        
    def setUp(self):
        self.patcher = patch('spambl.post')
        self.mocked_post = self.patcher.start()
        
        self.post_response = Mock()
        self.mocked_post.return_value = self.post_response
        
    def doTestForUnathorizedAPIKey(self, function):
        
        self.post_response.status_code = 401
        self.post_response.raise_for_status.side_effect = HTTPError
        
        self.assertRaises(UnathorizedAPIKeyError, function, self.valid_urls)
        
    def testContainsAnyForUnathorizedAPIKey(self):
        
        self.doTestForUnathorizedAPIKey(self.google_safe_browsing.contains_any)
        
    def testLookupForUnathorizedAPIKey(self):
        
        self.doTestForUnathorizedAPIKey(self.google_safe_browsing.lookup)
    
    def testContainsAnyForAnySpamUrls(self):
        
        self.post_response.status_code = 200
        
        actual = self.google_safe_browsing.contains_any(self.valid_urls)
        self.assertTrue(actual)
        
    def testContainsAnyForNonSpamUrls(self):
        
        self.post_response.status_code = 204
        
        actual = self.google_safe_browsing.contains_any(self.valid_urls)
        self.assertFalse(actual)
        
    def _setPostResult(self, classification):
        def mocked_post(_, body):
            urls = body.splitlines()[1:]
            classes = [classification.get(u, 'ok') for u in urls]
            
            response = Mock()
            response.status_code = 200
            response.content = '\n'.join(classes)
            
            return response
        
        self.mocked_post.side_effect = mocked_post
        
    @parameterized.expand([
                           ('HostnameUrls',
                            { 
                             'http://test1.com': 'phishing',
                             'http://test2.com': 'malware'
                             }),
                           ('IpV6Urls',
                            {
                             'https://123.22.1.11': 'unwanted',
                             'http://66.99.88.121': 'phishing, malware'
                             }),
                           ('IpV6Urls',
                            {
                             'http://[2001:DB8:abc:123::42]': 'phishing, malware',
                             'http://[3731:54:65fe:2::a7]': 'phishing, unwanted'
                             }),
                           ('SpamUrlsWithDuplicates',
                            {
                             'http://abc.com': 'malware, unwanted',
                             'http://domain.com': 'phishing, malware, unwanted'
                             }, 
                            ['http://abc.com'])
                           ])
    def testLookupFor(self, _, classification, duplicates = []):
        
        self._setPostResult(classification)
        
        item = lambda url, classes: AddressListItem(url, 
                                                    self.google_safe_browsing, 
                                                    classes.split(','))
        
        expected  = [item(u, c) for u, c in classification.items()]
                
        non_spam = ['http://nospam.com', 'https://nospam2.pl', 'https://spamfree.com']
        tested = classification.keys()+ duplicates + non_spam
        actual = self.google_safe_browsing.lookup(tested)
        
        self.assertItemsEqual(actual, expected)
        
    def testLookupForNonSpamUrls(self):
        ''' lookup should return an empty tuple when called for a sequence
        of non spam urls as argument '''
        
        self.post_response.status_code = 204
        
        actual = self.google_safe_browsing.lookup(self.valid_urls)
        self.assertFalse(actual)

    def tearDown(self):
        self.patcher.stop()
        
class HostCollectionTest(unittest.TestCase):
    
    valid_host_parameters = [
                     ('Host', 'test1.pl'),
                     ('IpV4', u'127.0.0.1'),
                     ('IpV6', u'2001:db8:abc:123::42')
                     ]
    
    invalid_host_parameters = [
                           ('Host', '-e'),
                           ('IpV4', u'999.999.000.111.222'),
                           ('IpV6', u'2001:db8:abcef:124::41')
                           ]
    
    def setUp(self):
        
        self.host_patcher = patch('spambl.host')
        self.host_mock = self.host_patcher.start()
        
        self.host_collection = HostCollection()
        
    @parameterized.expand(valid_host_parameters)
    def testAddForValid(self, _, value):
        
        new_item = Mock()
        self.host_mock.return_value = new_item
        
        self.host_collection.add(value)
        
        in_host_collection = new_item in self.host_collection.hosts
        
        self.assertTrue(in_host_collection)
        
    @parameterized.expand(invalid_host_parameters)
    def testAddForInvalid(self, _, value):
        
        self.host_mock.side_effect = ValueError
        
        self.assertRaises(ValueError, self.host_collection.add, value)
        
    @parameterized.expand(valid_host_parameters)
    def testContainsForListed(self, _, value):
        
        self.host_collection.hosts = [Mock()]
        
        self.assertTrue(value in self.host_collection)
        
    @parameterized.expand(valid_host_parameters)
    def testContainsForNotListed(self, _, value):
        
        self.assertFalse(value in self.host_collection)
        
    @parameterized.expand(invalid_host_parameters)
    def testContainsForInvalid(self, _, value):
        
        self.host_mock.side_effect = ValueError
        
        self.assertRaises(ValueError, self.host_collection.__contains__, value)
        
    def tearDown(self):
        self.host_patcher.stop()
            
class HostnameTest(unittest.TestCase):
    
    @parameterized.expand([
                           ('InvalidHostname', '-e'),
                           ('InvalidHostname', '/e'),
                           ('NonStringValue', 123)
                           ])
    def testConstructorFor(self, _, value):
        
        self.assertRaises(ValueError, Hostname, value)
    
    def _getHostnames(self, value_1, value_2):
        return map(Hostname, (value_1, value_2))
    
    def testIsMatchForTheSameDomains(self):
        
        value = 'hostname.pl'
        h_1, h_2 = self._getHostnames(value, value)
        
        self.assertTrue(h_1.is_match(h_2))
        self.assertTrue(h_2.is_match(h_1))
        
    def testIsMatchForDomainAndSubdomain(self):
        
        domain, subdomain = self._getHostnames('domain.com', 'sub.domain.com')
        
        self.assertTrue(subdomain.is_match(domain))
        self.assertFalse(domain.is_match(subdomain))
        
    def testIsMatchForUnrelatedDomains(self):
        
        h_1, h_2 = self._getHostnames('google.com', 'microsoft.com')
        
        self.assertFalse(h_1.is_match(h_2))
        self.assertFalse(h_2.is_match(h_1))
        
    def testIsMatchForHostnameAndAnotherObject(self):
        
        hostname = Hostname('hostname.pl')
        
        self.assertFalse(hostname.is_match([]))
        

class IpAddressTest(unittest.TestCase):
    ipv4_1 = u'255.0.2.1'
    ipv4_2 = u'122.44.55.99'
    ipv6_1 = u'2001:db8:abc:123::42'
    ipv6_2 = u'fe80::0202:b3ff:fe1e:8329'
    
    
    @parameterized.expand([
                           ('InvalidIpV4', u'299.0.0.1'),
                           ('InvalidIpV4', u'99.22.33.1.23'),
                           ('InvalidIpV6', u'2001:db8:abc:125::4h'),
                           ('InvalidIpV6', u'2001:db8:abcef:125::43'),
                           ('Hostname', u'abc.def.gh'),
                           ('NonUnicodeValue', '299.0.0.1')
                           ])
    def testConstructorFor(self, _, value):
        
        self.assertRaises(ValueError, IpAddress, value)
        
        
    @parameterized.expand([
                           ('IpV4', ipv4_1, reversename.ipv4_reverse_domain),
                           ('IpV6', ipv6_1, reversename.ipv6_reverse_domain)
                           ])
    def testRelativeDomainFor(self, _, value, expected_origin):
        
        ip_address = IpAddress(value)
        expected = reversename.from_address(value).relativize(expected_origin)
        
        self.assertEqual(expected, ip_address.relative_domain)
        
    @parameterized.expand([
                           ('IpV4Addresses', ipv4_1),
                           ('IpV6Addresses', ipv6_2),
                           ])
    def testIsMatchIsTrueForTheSame(self, _, value):
        first_ip = IpAddress(value)
        second_ip = IpAddress(unicode(value))
        
        self.assertTrue(first_ip.is_match(second_ip))
        self.assertTrue(second_ip.is_match(first_ip))
        
    @parameterized.expand([
                           ('DifferentIpV4Values', ipv4_1, ipv4_2),
                           ('IpV4AndIpV6', ipv4_1, ipv6_1),
                           ('DifferentIpV6Values', ipv6_1, ipv6_2),
                           ('IpV6AndIpV4', ipv6_1, ipv4_1)
                           ])
    def testIsMatchIsFalseFor(self, _, ip_value_1, ip_value_2):
        ip_1 = IpAddress(ip_value_1)
        ip_2 = IpAddress(ip_value_2)
        
        self.assertFalse(ip_1.is_match(ip_2))
        self.assertFalse(ip_2.is_match(ip_1))
        
    @parameterized.expand([
                           ('IpV4', ipv4_1),
                           ('IpV6', ipv6_1),
                           ])
    def testIsMatchIsFalseForANonIpValueAnd(self, _, ip_value):
        
        ip = IpAddress(ip_value)
        other = []
        
        self.assertFalse(ip.is_match(other))
        
class HostTest(unittest.TestCase):
    
    def setUp(self):
        
        self.ipaddress_patcher = patch('spambl.IpAddress')
        self.ipaddress_mock = self.ipaddress_patcher.start()
        
        self.hostname_patcher = patch('spambl.Hostname')
        self.hostname_mock = self.hostname_patcher.start()
        
    @parameterized.expand([
                           ('V4',  u'127.0.0.1'),
                           ('V6', u'2001:db8:abc:125::45'),
                           ])
    def testHostForValidIp(self, _, value):
        ip_address = Mock()
        self.ipaddress_mock.return_value = ip_address
        
        actual_ip = host(value)
        
        self.assertEqual(ip_address, actual_ip)
        
    def testHostForHostname(self):
        
        hostname_str = 'test.hostname'
        
        hostname_mock = Mock()
        self.hostname_mock.return_value = hostname_mock
        
        self.ipaddress_mock.side_effect = ValueError
        
        actual_hostname = host(hostname_str)
        
        self.assertEqual(hostname_mock, actual_hostname)
        
    @parameterized.expand([
                           ('IpV4Address', u'299.0.0.1'),
                           ('IpV4Address', u'99.22.33.1.23'),
                           ('IpV6Address', u'2001:db8:abc:125::4h'),
                           ('IpV6Address', u'2001:db8:abcef:125::43'),
                           ('Hostname', '-e'),
                           ('Hostname', '/e')
                           ])
    def testHostForInvalid(self, _, value):
        
        self.hostname_mock.side_effect = ValueError
        self.ipaddress_mock.side_effect = ValueError
        
        self.assertRaises(ValueError, host, value)
        
    def tearDown(self):
        self.ipaddress_patcher.stop()
        self.hostname_patcher.stop()
          
class IsValidUrlTest(unittest.TestCase):
    
    @parameterized.expand([
                           ('WithHttpScheme', 'http://test.url.com'),
                           ('WithHttpsScheme', 'https://google.com'),
                           ('WithFtpScheme', 'ftp://ftp.test.com'),
                           ('WithNumericHost', 'http://999.com'),
                           ('EndingWithSlash', 'https://google.com/'),
                           ('WithPathQueryAndFragment', 'https://test.domain.com/path/element?var=1&var_2=3#fragment'),
                           ('WithQuery', 'http://test.domain.com?var_1=1&var_2=2'),
                           ('WithPath', 'http://test.domain.com/path'),
                           ('WithPathAndFragement', 'http://test.domain.com/path#fragment'),
                           ('WithQueryAndFragment', 'http://test.domain.com?var_1=1&var_2=2#fragment'),
                           ('WithPort', 'https://test.domain.com:123'),
                           ('WithAuthentication', 'https://abc:def@test.domain.com'),
                           ('WithIpV4Host', 'http://255.0.0.255'),
                           ('WithIpV6Host', 'http://[2001:db8:abc:125::45]')
                           ])
    def testIsValidUrlForValidUrl(self, _, url):
        self.assertTrue(is_valid_url(url))
             
    @parameterized.expand([
                           ('MissingSchema', 'test.url.com'),
                           ('WithInvalidIpAddressV6', 'http://266.0.0.266'),
                           ('WithInvalidIPAddressV6', 'http://127.0.0.1.1'),
                           ('WithInvalidPort', 'http://test.domain.com:aaa'),
                           ('MissingTopLevelDomain', 'https://testdomaincom'),
                           ('WithInvalidHostname', 'http://-invalid.domain.com')
                           ])
    def testIsValidUrlForInvalidUrl(self, _, url):
        self.assertFalse(is_valid_url(url))
            
class RedirectUrlResolverTest(unittest.TestCase):
    
    valid_urls = ['http://first.com', 'http://122.55.33.21',
    'http://[2001:db8:abc:123::42]']
    
    def setUp(self):
        
        session_mock = Mock()
        
        self.head_mock = session_mock.head
        self.resolve_redirects_mock = session_mock.resolve_redirects
        
        self.resolver = RedirectUrlResolver(session_mock)
        
        self.patcher = patch('spambl.is_valid_url')
        self.is_valid_url_mock = self.patcher.start()
        
        
    def testGetFirstResponseForInvalidUrl(self):
        
        self.is_valid_url_mock.return_value = False
        
        self.assertRaises(ValueError, self.resolver.get_first_response, 'http://test.com')
        
    @parameterized.expand([
                           ('ConnectionError', ConnectionError),
                           ('InvalidSchema', InvalidSchema),
                           ('Timeout', Timeout)
                           ])
    def testGetFirstResponseForFirstUrlTriggering(self, _, exception_type):
        
        self.head_mock.side_effect = exception_type
        self.assertIsNone(self.resolver.get_first_response('http://test.com'))
        
    def testGetRedirectUrlsForInvalidUrl(self):
        
        self.is_valid_url_mock.return_value = False
        
        with self.assertRaises(ValueError):
            self.resolver.get_redirect_urls('http://test.com').next()
        
    @parameterized.expand([
                           ('ConnectionError', ConnectionError),
                           ('InvalidSchema', InvalidSchema),
                           ('Timeout', Timeout)
                           ])
    def testGetRedirectUrlsForFirstUrlTriggering(self, _, exception_type):
        
        self.head_mock.side_effect = exception_type
        
        url_generator = self.resolver.get_redirect_urls('http://test.com')
        
        self.assertFalse(list(url_generator))
            
    def _getResponseMocks(self, urls):
        
        response_mocks = []
        
        for u in urls:
            response = Mock()
            response.url = u
            response_mocks.append(response)
            
        return response_mocks
    
    def _setSessionResolveRedirectsSideEffects(self, urls, exception_type=None):
        
        if not (exception_type is None or 
                issubclass(exception_type, Exception)):
            raise ValueError, '{} is not a subclass of Exception'.format(exception_type)
        
        self._response_mocks = self._getResponseMocks(urls)
        
        def resolveRedirects(response, request):
            for r in self._response_mocks:
                yield r
                
            if exception_type:
                raise exception_type
                
        self.resolve_redirects_mock.side_effect = resolveRedirects
        
    def _setLastResponseLocationHeader(self, url):
        
        all_responses = [self.head_mock.return_value] + self._response_mocks
        all_responses[-1].headers = {'location': url}
    
    def _testGetRedirectUrlsYields(self, expected):
        
        url_generator = self.resolver.get_redirect_urls('http://test.com')
        
        self.assertEqual(expected, list(url_generator))
        
    @parameterized.expand([
                           ('YieldingNoUrl', []),
                           ('YieldingUrls', valid_urls)
                           ])
    def testGetRedirectUrls(self, _, expected):
        
        self._setSessionResolveRedirectsSideEffects(expected)
        
        self._testGetRedirectUrlsYields(expected)
        
    @parameterized.expand([
                           ('Timeout', [], Timeout),
                           ('Timeout', valid_urls, Timeout),
                           ('ConnectionError', [], ConnectionError),
                           ('ConnectionError', valid_urls, ConnectionError),
                           ('InvalidSchema', [], InvalidSchema),
                           ('InvalidSchema', valid_urls, InvalidSchema),
                           ])
    def testGetRedirectUrlsUntilValidUrlTriggers(self, _, expected, exception_type):
        
        self._setSessionResolveRedirectsSideEffects(expected, exception_type)
        
        error_source = 'http://triggered.error.com'
        expected.append(error_source)
        
        self._setLastResponseLocationHeader(error_source)
            
        self._testGetRedirectUrlsYields(expected)
        
    @parameterized.expand([
                           ('InvalidURL', [], InvalidURL),
                           ('InvalidURL', valid_urls, InvalidURL),
                           ('ConnectionError', [], ConnectionError),
                           ('ConnectionError', valid_urls, ConnectionError),
                           ('InvalidSchema', [], InvalidSchema),
                           ('InvalidSchema', valid_urls, InvalidSchema),
                           ])
    def testGetRedirectUrlsUntilInvalidUrlTriggers(self, _, expected, exception_type):
        
        is_valid_url = lambda u: u in expected+['http://test.com']
        self.is_valid_url_mock.side_effect = is_valid_url
        
        self._setSessionResolveRedirectsSideEffects(expected, exception_type)
        
        self._setLastResponseLocationHeader('http://invalid.url.com')
            
        self._testGetRedirectUrlsYields(expected)
    
    def tearDown(self):
        
        self.patcher.stop()
        
            
class BaseUrlTesterTest(unittest.TestCase):
    
    urls_and_redirects_test_input = [
                                     ('NoRedirects',
                                      ('http://url1.com', 'http://59.99.63.88'),
                                      {}),
                                     ('DuplicateInputUrlsAndNoRedirects',
                                      ('http://url1.com', 'http://url1.com', 'http://59.99.63.88'),
                                      {}),
                                     ('Redirects',
                                      ('http://abc.com', 'https://67.23.21.11', 'http://foo.com'),
                                      {
                                       'http://abc.com': ['http://xyz.pl', 'http://final.com'],
                                       'http://foo.com': ['http://bar.com']
                                       }),
                                     ('DuplicateInputUrlsAndUniqueRedirects',
                                      ('http://abc.com', 'https://67.23.21.11', 'http://abc.com'),
                                      {
                                       'http://abc.com': ['http://xyz.pl', 'http://final.com'],
                                       }),
                                     ('DuplicateRedirectUrls',
                                      ('http://abc.com', 'https://67.23.21.11', 'http://foo.com'),
                                      {
                                       'http://abc.com': ['http://xyz.pl', 'http://final.com'],
                                       'http://foo.com': ['http://xyz.pl', 'http://final.com']
                                       }),
                                     ('DuplicateInputUrlsAndRedirects',
                                      ('http://abc.com', 'https://67.23.21.11', 'https://67.23.21.11'),
                                      {
                                       'http://abc.com': ['http://xyz.pl', 'http://final.com'],
                                       'https://67.23.21.11': ['http://xyz.pl', 'http://final.com']
                                       })
                                     ]
    
    def setUp(self):
        
        self.url_tester = BaseUrlTester()
        
        resolver_mock = Mock()
        
        self.resolver_get_redirect_urls_mock = resolver_mock.get_redirect_urls
        
        self.url_tester._redirect_url_resolver = resolver_mock
        
        self.is_valid_url_patcher = patch('spambl.is_valid_url')
        self.is_valid_url_mock = self.is_valid_url_patcher.start()
        
    @parameterized.expand([
                           ('OneInvalidUrl', ('http://-xyz.com',), False),
                           ('OneInvalidUrlAndRedirectResolution', ('http://-xyz.com',), True),
                           ('TwoInvalidUrls', ('http://-xyz.com', 'http://999.999.999.999.11'), False),
                           ('TwoInvalidUrlsAndRedirectResolution', ('http://-xyz.com', 'http://999.999.999.999.11'), True)
                           ])
    def testGetUrlsToTestFor(self, _, invalid_urls, resolve_redirects):
        
        self.is_valid_url_mock.side_effect = lambda u: u in invalid_urls
        
        urls = ('http://valid.com', 'http://122.55.29.11') + invalid_urls
        
        with self.assertRaises(ValueError):
            list(self.url_tester.get_urls_to_test(urls, resolve_redirects))
        
    @parameterized.expand([
                           ('', ('http://url1.com', 'https://122.56.65.99', 'https://google.com')),
                           ('WithDuplicatesInInput', ('http://abc.com', 'http://66.33.22.11', 'http://abc.com'))
                           ])
    def testGetUrlsToTestForValidUrls(self, _, input_args):
        
        expected = list(set(input_args))
        
        actual = list(self.url_tester.get_urls_to_test(input_args, False))
        
        self.assertItemsEqual(expected, actual)
        
    def _setResolverGetRedirectUrlsResult(self, urls_to_redirect_urls):
        def get_redirect_urls(url):
            
            urls = urls_to_redirect_urls.get(url, [])
            
            for u in urls:
                yield u
        
        self.resolver_get_redirect_urls_mock.side_effect = get_redirect_urls
        
    @parameterized.expand(urls_and_redirects_test_input )
    def testGetRedirectUrlsFor(self, _, input_args, input_to_redirect_urls):
        
        self._setResolverGetRedirectUrlsResult(input_to_redirect_urls)
        expected = set(chain(*input_to_redirect_urls.values()))
        actual = list(self.url_tester.get_redirect_urls(input_args))
        
        self.assertItemsEqual(expected, actual)
    
    @parameterized.expand(urls_and_redirects_test_input )
    def testGetUrlsToTestWithRedirectResolutionFor(self, _, input_args, input_to_redirect_urls):
        
        self._setResolverGetRedirectUrlsResult(input_to_redirect_urls)
        
        expected = set(chain(input_args, *input_to_redirect_urls.values()))
        actual = list(self.url_tester.get_urls_to_test(input_args, True))
        
        self.assertItemsEqual(expected, actual)
        
    @parameterized.expand([
                           ('AndBeingUnique',
                            ('http://first.com', 'https://122.55.66.29'),
                            {'http://first.com': ['http://redirect.com'],
                             'https://122.55.66.29': ['http://abc.pl', 'http://xyz.com']
                             }),
                           ('AndSomeBeingTheSame',
                            ('http://first.com', 'http://first.redirect.com'),
                            {'http://first.com': ['http://first.redirect.com', 'http://second.redirect.com']
                             })
                           ])
    def testGetUrlsToTestForRedirectUrlsFollowingInputUrls(self, _, input_args, input_to_redirect_urls):
        
        self._setResolverGetRedirectUrlsResult(input_to_redirect_urls)
        
        original_urls = set(input_args)
        redirect_urls = set(chain(*input_to_redirect_urls.values()))
        
        number_of_original_urls = len(original_urls)
        
        actual = list(self.url_tester.get_urls_to_test(input_args, True))
        
        first_part = actual[:number_of_original_urls]
        second_part = actual[number_of_original_urls:]
        
        self.assertItemsEqual(original_urls, first_part)
        
        self.assertTrue(set(second_part).issubset(redirect_urls))
        
    def tearDown(self):
        self.is_valid_url_patcher.stop()
        
        
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()