"""Bounded image reads and HTTPS downloads restricted to Instagram media hosts."""

import ipaddress
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .config import MAX_IMAGE_BYTES, MAX_IMAGES, REQUEST_SECONDS, RETRY_ATTEMPTS
    from .runtime_utils import ScraperError, http_failure, retry_call
else:
    from config import MAX_IMAGE_BYTES, MAX_IMAGES, REQUEST_SECONDS, RETRY_ATTEMPTS
    from runtime_utils import ScraperError, http_failure, retry_call


def image_mime(data):
    """Identify file signatures; an extension or HTTP Content-Type is not proof."""
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 33 and data[12:16] == b'IHDR':
        return 'image/png'
    if len(data) >= 4 and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):
        return 'image/jpeg'
    if (len(data) >= 20 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'
            and data[12:16] in {b'VP8 ', b'VP8L', b'VP8X'}
            and int.from_bytes(data[4:8], 'little') + 8 == len(data)):
        return 'image/webp'
    # This is a format/signature check, not a complete image decoder.
    raise ScraperError('image_validation', 'invalid_image', 'Image bytes are not recognizable JPEG, PNG, or WebP.')


def read_local_images(filenames):
    """Check sizes before allocating memory, then cap reads in case files grow."""
    if not 1 <= len(filenames) <= MAX_IMAGES:
        raise ScraperError('image_validation', 'image_count', f'Provide 1–{MAX_IMAGES} images.')
    images, total = [], 0
    for filename in filenames:
        path = Path(filename)
        remaining = MAX_IMAGE_BYTES - total
        if not path.is_file() or path.stat().st_size > remaining:
            raise ScraperError('image_validation', 'file_size', 'Images must be regular files totaling at most 10 MB.')
        with path.open('rb') as source:
            data = source.read(remaining + 1)
        if len(data) > remaining:
            raise ScraperError('image_validation', 'file_size', 'Images exceed the 10 MB limit.')
        images.append((data, image_mime(data)))
        total += len(data)
    return images


def media_target(url):
    """Allow only HTTPS Instagram CDNs resolving exclusively to public IPs."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        allowed = any(host.endswith('.' + domain) for domain in ('cdninstagram.com', 'fbcdn.net'))
        if (parsed.scheme != 'https' or not allowed or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError('Disallowed URL')
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = [item[4][0] for item in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('Nonpublic address')
        return host, ips[0], parsed.path + ('?' + parsed.query if parsed.query else '')
    except (ValueError, TypeError):
        raise ScraperError('download', 'unsafe_url', 'Image URL is not an approved public HTTPS media address.') from None
    except socket.gaierror:
        raise ScraperError('download', 'dns_error', 'Image host could not be resolved.', True) from None


def download_image(url, remaining):
    """Pin the validated IP, retain TLS hostname checks, and never follow redirects."""
    import certifi
    import urllib3

    def download_once():
        host, ip, target = media_target(url)
        deadline = time.monotonic() + REQUEST_SECONDS
        # Connecting directly to the checked IP prevents a second DNS lookup from
        # redirecting us to an internal host. SNI/certificate checks still use host.
        pool = urllib3.HTTPSConnectionPool(ip, port=443, server_hostname=host,
            assert_hostname=host, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        response = None
        try:
            response = pool.urlopen('GET', target or '/', headers={'Host': host, 'Accept-Encoding': 'identity'},
                preload_content=False, redirect=False, retries=False,
                timeout=urllib3.Timeout(connect=5, read=5, total=REQUEST_SECONDS))
            if response.status != 200:
                raise http_failure('download', response.status)
            data = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise ScraperError('download', 'timeout', 'Image download exceeded its time limit.', True)
                chunk = response.read1(min(65536, remaining - len(data) + 1), decode_content=False)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > remaining:
                    raise ScraperError('download', 'image_size', 'Post images exceed the 10 MB limit.')
            return bytes(data), image_mime(data)
        except urllib3.exceptions.HTTPError:
            raise ScraperError('download', 'connection_error', 'Secure image download failed.', True) from None
        finally:
            if response is not None:
                response.close()
            pool.close()
    return retry_call(download_once, RETRY_ATTEMPTS)
