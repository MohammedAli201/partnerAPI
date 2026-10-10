"""HTTPS to an approved pinned IP, preserving hostname verification and SNI."""
import http.client
import ipaddress
import socket
import ssl
import threading
from urllib.parse import urlsplit,urlunsplit
TLS_CONTEXT=ssl.create_default_context()


def endpoint_url(url):
    if not isinstance(url,str) or any(ord(c)<33 or ord(c)==127 for c in url) or '\\' in url:
        raise ValueError('Invalid webhook URL')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError('Webhook must use HTTPS without credentials or fragment')
    if parsed.port not in (None,443):
        raise ValueError('Only webhook port 443 is permitted')
    if '%' in parsed.hostname or parsed.hostname.endswith('.'):
        raise ValueError('Ambiguous hostname')
    host=parsed.hostname.encode('idna').decode('ascii').lower()
    hostpart=f'[{host}]' if ':' in host else host
    return urlunsplit(('https',hostpart,parsed.path or '/',parsed.query,''))


def public_ip(value):
    address=ipaddress.ip_address(value)
    if isinstance(address,ipaddress.IPv6Address) and address.ipv4_mapped:
        address=address.ipv4_mapped
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise ValueError('Prohibited webhook address')
    # IPv6 translation/tunnel ranges are denied to prevent private IPv4 encapsulation.
    if address.version==6 and any(address in ipaddress.ip_network(n) for n in ('64:ff9b::/96','64:ff9b:1::/48','2002::/16','2001::/32')):
        raise ValueError('IPv6 transition addresses are prohibited')
    return str(address)


def resolve(url,resolver=None):
    parsed=urlsplit(endpoint_url(url))
    resolver=resolver or socket.getaddrinfo
    answers=resolver(parsed.hostname,443,type=socket.SOCK_STREAM)
    addresses=sorted({public_ip(answer[4][0]) for answer in answers})
    if not addresses:
        raise ValueError('No approved addresses')
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,hostname,address):
        super().__init__(hostname,443,timeout=5,context=TLS_CONTEXT)
        self.address=address

    def connect(self):
        # Construct a numeric sockaddr directly: no second hostname lookup and no
        # environment proxy. TLS still verifies the registered hostname via SNI.
        address=ipaddress.ip_address(self.address)
        family=socket.AF_INET6 if address.version==6 else socket.AF_INET
        raw=socket.socket(family,socket.SOCK_STREAM)
        raw.settimeout(self.timeout)
        try:
            raw.connect((str(address),443,0,0) if family==socket.AF_INET6 else (str(address),443))
            self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close()
            raise

    def abort(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()


def send(url,approved,body,headers):
    url=endpoint_url(url)
    current=resolve(url)
    allowed={public_ip(ip) for ip in approved}
    if not set(current).issubset(allowed):
        raise ValueError('DNS changed; endpoint requires reapproval')
    parsed=urlsplit(url)
    connection=PinnedHTTPS(parsed.hostname,current[0])
    deadline=threading.Timer(10,getattr(connection,'abort',connection.close))
    deadline.daemon=True
    deadline.start()
    try:
        path=parsed.path+('?' + parsed.query if parsed.query else '')
        connection.request('POST',path,body=body,headers={**headers,'Host':parsed.netloc})
        response=connection.getresponse()
        # Do not follow any 3xx, and do not read an unbounded response body.
        return response.status
    finally:
        deadline.cancel()
        connection.close()
