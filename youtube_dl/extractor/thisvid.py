# coding: utf-8
from __future__ import unicode_literals

import re
import itertools

from .common import InfoExtractor
from ..compat import (
    compat_urlparse,
    compat_str,
)
from ..utils import (
    clean_html,
    get_element_by_class,
    int_or_none,
    merge_dicts,
    js_to_json,
    url_or_none,
    parse_resolution,
    urljoin,
)


class ThisVidIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?thisvid\.com/(?P<type>videos|embed)/(?P<id>[A-Za-z0-9-]+)'
    _TESTS = [{
        'url': 'https://thisvid.com/videos/sitting-on-ball-tight-jeans/',
        'md5': '839becb572995687e11a69dc4358a386',
        'info_dict': {
            'id': '3533241',
            'ext': 'mp4',
            'title': 'Sitting on ball tight jeans',
            'description': 'md5:372353bb995883d1b65fddf507489acd',
            'thumbnail': r're:https?://\w+\.thisvid\.com/(?:[^/]+/)+3533241/preview\.jpg',
            'uploader_id': '150629',
            'uploader': 'jeanslevisjeans',
            'age_limit': 18,
        }
    }, {
        'url': 'https://thisvid.com/embed/3533241/',
        'md5': '839becb572995687e11a69dc4358a386',
        'info_dict': {
            'id': '3533241',
            'ext': 'mp4',
            'title': 'Sitting on ball tight jeans',
            'thumbnail': r're:https?://\w+\.thisvid\.com/(?:[^/]+/)+3533241/preview\.jpg',
            'uploader_id': '150629',
            'uploader': 'jeanslevisjeans',
            'age_limit': 18,
        }
    }]

    def _extract_kvs(self, url, webpage, video_id):

        def getlicensetoken(license):
            modlicense = license.replace('$', '').replace('0', '1')
            center = int(len(modlicense) / 2)
            fronthalf = int(modlicense[:center + 1])
            backhalf = int(modlicense[center:])

            modlicense = compat_str(4 * abs(fronthalf - backhalf))

            def parts():
                for o in range(0, center + 1):
                    for i in range(1, 5):
                        yield compat_str((int(license[o + i]) + int(modlicense[o])) % 10)

            return ''.join(parts())

        def getrealurl(video_url, license_code):
            if not video_url.startswith('function/0/'):
                return video_url  # not obfuscated

            url_path, _, url_query = video_url.partition('?')
            urlparts = url_path.split('/')[2:]
            license = getlicensetoken(license_code)
            newmagic = urlparts[5][:32]

            def spells(x, o):
                l = (o + sum(int(n) for n in license[o:])) % 32
                for i in range(0, len(x)):
                    yield {l: x[o], o: x[l]}.get(i, x[i])

            for o in range(len(newmagic) - 1, -1, -1):
                newmagic = ''.join(spells(newmagic, o))

            urlparts[5] = newmagic + urlparts[5][32:]
            return '/'.join(urlparts) + '?' + url_query

        flashvars = self._search_regex(
            r'(?s)<script\b[^>]*>.*?var\s+flashvars\s*=\s*(\{.+?\});.*?</script>',
            webpage, 'flashvars')
        flashvars = self._parse_json(flashvars, video_id, transform_source=js_to_json)

        # extract the part after the last / as the display_id from the
        # canonical URL.
        display_id = self._search_regex(
            r'(?:<link href="https?://[^"]+/(.+?)/?" rel="canonical"\s*/?>'
            r'|<link rel="canonical" href="https?://[^"]+/(.+?)/?"\s*/?>)',
            webpage, 'display_id', fatal=False
        )
        title = self._html_search_regex(r'<(?:h1|title)>(?:Video: )?(.+?)</(?:h1|title)>', webpage, 'title')

        thumbnail = flashvars['preview_url']
        if thumbnail.startswith('//'):
            protocol, _, _ = url.partition('/')
            thumbnail = protocol + thumbnail

        url_keys = list(filter(re.compile(r'^video_(?:url|alt_url\d*)$').match, flashvars.keys()))
        formats = []
        for key in url_keys:
            if '/get_file/' not in flashvars[key]:
                continue
            format_id = flashvars.get(key + '_text', key)
            formats.append(merge_dicts(
                parse_resolution(format_id) or parse_resolution(flashvars[key]), {
                    'url': getrealurl(flashvars[key], flashvars['license_code']),
                    'format_id': format_id,
                    'ext': 'mp4',
                    'http_headers': {'Referer': url},
                }))
            if not formats[-1].get('height'):
                formats[-1]['quality'] = 1

        self._sort_formats(formats)

        return {
            'id': flashvars['video_id'],
            'display_id': display_id,
            'title': title,
            'thumbnail': thumbnail,
            'formats': formats,
        }

    def _real_extract(self, url):
        main_id, type_ = re.match(self._VALID_URL, url).group('id', 'type')
        webpage = self._download_webpage(url, main_id)

        title = self._html_search_regex(
            r'<title\b[^>]*?>(?:Video:\s+)?(.+?)(?:\s+-\s+ThisVid(?:\.com| tube))?</title>',
            webpage, 'title')

        if type_ == 'embed':
            # look for more metadata
            video_alt_url = url_or_none(self._search_regex(
                r'''video_alt_url\s*:\s+'(%s/)',''' % (self._VALID_URL, ),
                webpage, 'video_alt_url', default=None))
            if video_alt_url and video_alt_url != url:
                webpage = self._download_webpage(
                    video_alt_url, main_id,
                    note='Redirecting embed to main page', fatal=False) or webpage

        video_holder = get_element_by_class('video-holder', webpage) or ''
        if '>This video is a private video' in video_holder:
            self.raise_login_required(
                (clean_html(video_holder) or 'Private video').split('\n', 1)[0])

        uploader = self._html_search_regex(
            r'''(?s)<span\b[^>]*>Added by:\s*</span><a\b[^>]+\bclass\s*=\s*["']author\b[^>]+\bhref\s*=\s*["']https://thisvid\.com/members/([0-9]+/.{3,}?)\s*</a>''',
            webpage, 'uploader', default='')
        uploader = re.split(r'''/["'][^>]*>\s*''', uploader)
        if len(uploader) == 2:
            # id must be non-empty, uploader could be ''
            uploader_id, uploader = uploader
            uploader = uploader or None
        else:
            uploader_id = uploader = None

        video_id = self._generic_id(url)

        info_dict = {
            # '_type': 'url_transparent',
            'title': title,
            'age_limit': 18,
            'uploader': uploader,
            'uploader_id': uploader_id,
        }

        # request = sanitized_Request(url)
        # request.add_header('Accept-Encoding', '*')
        # full_response = self._request_webpage(request, video_id)
        # first_bytes = full_response.read(512)
        # webpage = self._webpage_read_content(full_response, url, video_id, prefix=first_bytes)

        return merge_dicts(self._extract_kvs(url, webpage, video_id), info_dict)

        return merge_dicts({
            '_type': 'url_transparent',
            'title': title,
            'age_limit': 18,
            'uploader': uploader,
            'uploader_id': uploader_id,
        }, self.url_result(url, ie='Generic'))


class ThisVidMemberIE(InfoExtractor):
    _VALID_URL = r'https?://thisvid\.com/members/(?P<id>\d+)'
    _TESTS = [{
        'url': 'https://thisvid.com/members/2140501/',
        'info_dict': {
            'id': '2140501',
            'title': 'Rafflesia\'s Profile',
        },
        'playlist_mincount': 16,
    }, {
        'url': 'https://thisvid.com/members/2140501/favourite_videos/',
        'info_dict': {
            'id': '2140501',
            'title': 'Rafflesia\'s Favourite Videos',
        },
        'playlist_mincount': 15,
    }, {
        'url': 'https://thisvid.com/members/636468/public_videos/',
        'info_dict': {
            'id': '636468',
            'title': 'Happymouth\'s Public Videos',
        },
        'playlist_mincount': 196,
    },
    ]

    def _urls(self, html):
        for m in re.finditer(r'''<a\b[^>]+\bhref\s*=\s*["'](?P<url>%s\b)[^>]+>''' % (ThisVidIE._VALID_URL, ), html):
            yield m.group('url')

    def _real_extract(self, url):
        pl_id = self._match_id(url)
        webpage = self._download_webpage(url, pl_id)

        title = re.split(
            r'(?i)\s*\|\s*ThisVid\.com\s*$',
            self._og_search_title(webpage, default=None) or self._html_search_regex(r'(?s)<title\b[^>]*>(.+?)</title', webpage, 'title', fatal=False) or '', 1)[0] or None

        def entries(page_url, html=None):
            for page in itertools.count(1):
                if not html:
                    html = self._download_webpage(
                        page_url, pl_id, note='Downloading page %d' % (page, ),
                        fatal=False) or ''
                for u in self._urls(html):
                    yield u
                next_page = get_element_by_class('pagination-next', html) or ''
                if next_page:
                    # member list page
                    next_page = urljoin(url, self._search_regex(
                        r'''<a\b[^>]+\bhref\s*=\s*("|')(?P<url>(?!#)(?:(?!\1).)+)''',
                        next_page, 'next page link', group='url', default=None))
                # in case a member page should have pagination-next with empty link, not just `else:`
                if next_page is None:
                    # playlist page
                    parsed_url = compat_urlparse.urlparse(page_url)
                    base_path, num = parsed_url.path.rsplit('/', 1)
                    num = int_or_none(num)
                    if num is None:
                        base_path, num = parsed_url.path.rstrip('/'), 1
                    parsed_url = parsed_url._replace(path=base_path + ('/%d' % (num + 1, )))
                    next_page = compat_urlparse.urlunparse(parsed_url)
                    if page_url == next_page:
                        next_page = None
                if not next_page:
                    break
                page_url, html = next_page, None

        return self.playlist_from_matches(
            entries(url, webpage), playlist_id=pl_id, playlist_title=title, ie='ThisVid')


class ThisVidPlaylistIE(ThisVidMemberIE):
    _VALID_URL = r'https?://thisvid\.com/playlist/(?P<id>\d+)/video/(?P<video_id>[A-Za-z0-9-]+)'
    _TESTS = [{
        'url': 'https://thisvid.com/playlist/6615/video/big-italian-booty-28/',
        'info_dict': {
            'id': '6615',
            'title': 'Underwear Stuff',
        },
        'playlist_mincount': 200,
    }, {
        'url': 'https://thisvid.com/playlist/6615/video/big-italian-booty-28/',
        'info_dict': {
            'id': '1072387',
            'ext': 'mp4',
            'title': 'Big Italian Booty 28',
            'description': 'md5:1bccf7b13765e18fb27bf764dba7ede2',
            'uploader_id': '367912',
            'uploader': 'Jcmusclefun',
            'age_limit': 18,
        },
        'params': {
            'noplaylist': True,
        },
    }]

    def _get_video_url(self, pl_url):
        video_id = re.match(self._VALID_URL, pl_url).group('video_id')
        return urljoin(pl_url, '/videos/%s/' % (video_id, ))

    def _urls(self, html):
        for m in re.finditer(r'''<a\b[^>]+\bhref\s*=\s*["'](?P<url>%s\b)[^>]+>''' % (self._VALID_URL, ), html):
            yield self._get_video_url(m.group('url'))

    def _real_extract(self, url):
        pl_id = self._match_id(url)

        if self._downloader.params.get('noplaylist'):
            self.to_screen('Downloading just the featured video because of --no-playlist')
            return self.url_result(self._get_video_url(url), 'ThisVid')

        self.to_screen(
            'Downloading playlist %s - add --no-playlist to download just the featured video' % (pl_id, ))
        result = super(ThisVidPlaylistIE, self)._real_extract(url)

        # rework title returned as `the title - the title`
        title = result['title']
        t_len = len(title)
        if t_len > 5 and t_len % 2 != 0:
            t_len = t_len // 2
            if title[t_len] == '-':
                title = [t.strip() for t in (title[:t_len], title[t_len + 1:])]
                if title[0] and title[0] == title[1]:
                    result['title'] = title[0]
        return result
