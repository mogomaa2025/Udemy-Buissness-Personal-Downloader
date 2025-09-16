from gui import show_video_selection_window
# -*- coding: utf-8 -*-
import argparse
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import IO, Union
from utils import find_executable

import browser_cookie3
import demoji
import m3u8
import requests
import yt_dlp
from bs4 import BeautifulSoup
from coloredlogs import ColoredFormatter
from dotenv import load_dotenv
from pathvalidate import sanitize_filename
from requests.exceptions import ConnectionError as conn_error
from tqdm import tqdm

from constants import *
from tls import SSLCiphers
from vtt_to_srt import convert

DOWNLOAD_DIR = os.path.join(os.getcwd(), "out_dir")

retry = 3
downloader = None
logger: logging.Logger = None
dl_assets = False
dl_captions = False
dl_quizzes = False
skip_lectures = False
caption_locale = "en"
quality = None
bearer_token = None
portal_name = None
course_name = None
keep_vtt = False
skip_hls = False
concurrent_downloads = 10
save_to_file = None
load_from_file = None
course_url = None
info = None
# keys variable removed - decryption now handled by GUI
id_as_course_name = False
is_subscription_course = False
use_h265 = False
h265_crf = 28
h265_preset = "medium"
use_nvenc = False
browser = None
cj = None
use_continuous_lecture_numbers = False
chapter_filter = None
lecture_filter = None


def deEmojify(inputStr: str):
    return demoji.replace(inputStr, "")


# from https://stackoverflow.com/a/21978778/9785713
def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ""):
            logger.debug("[%s]: %r", prefix, line.decode("utf8").strip())
        pipe.flush()


def parse_chapter_filter(chapter_str: str):
    """
    Given a string like "1,3-5,7,9-11", return a set of chapter numbers.
    """
    chapters = set()
    for part in chapter_str.split(','):
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                chapters.update(range(start, end + 1))
            except ValueError:
                logger.error("Invalid range in --chapter argument: %s", part)
        else:
            try:
                chapters.add(int(part.strip()))
            except ValueError:
                logger.error("Invalid chapter number in --chapter argument: %s", part)
    return chapters


def parse_lecture_filter(lecture_str: str):
    """
    Given a string like "1,3-5,7,9-11", return a set of lecture numbers.
    """
    lectures = set()
    for part in lecture_str.split(','):
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                lectures.update(range(start, end + 1))
            except ValueError:
                logger.error("Invalid range in --lecture argument: %s", part)
        else:
            try:
                lectures.add(int(part.strip()))
            except ValueError:
                logger.error("Invalid lecture number in --lecture argument: %s", part)
    return lectures


# this is the first function that is called, we parse the arguments, setup the logger, and ensure that required directories exist
def pre_run():
    global dl_assets, dl_captions, dl_quizzes, skip_lectures, caption_locale, quality, bearer_token, course_name, keep_vtt, skip_hls, concurrent_downloads, load_from_file, save_to_file, bearer_token, course_url, info, logger, id_as_course_name, LOG_LEVEL, use_h265, h265_crf, h265_preset, use_nvenc, browser, is_subscription_course, DOWNLOAD_DIR, use_continuous_lecture_numbers, chapter_filter, lecture_filter

    # make sure the logs directory exists
    if not os.path.exists(LOG_DIR_PATH):
        os.makedirs(LOG_DIR_PATH, exist_ok=True)

    parser = argparse.ArgumentParser(description="Udemy Downloader")
    parser.add_argument(
        "-c", "--course-url", dest="course_url", type=str, help="The URL of the course to download", required=True
    )
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        help="The Bearer token to use",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int,
        help="Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not specified, the best quality will be downloaded for each lecture",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help="The language to download for captions, specify 'all' to download all captions (Default is 'en')",
    )
    parser.add_argument(
        "-cd",
        "--concurrent-downloads",
        dest="concurrent_downloads",
        type=int,
        help="The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)",
    )
    parser.add_argument(
        "--skip-lectures",
        dest="skip_lectures",
        action="store_true",
        help="If specified, lectures won't be downloaded",
    )
    parser.add_argument(
        "--download-assets",
        dest="download_assets",
        action="store_true",
        help="If specified, lecture assets will be downloaded",
    )
    parser.add_argument(
        "--download-captions",
        dest="download_captions",
        action="store_true",
        help="If specified, captions will be downloaded",
    )
    parser.add_argument(
        "--download-quizzes",
        dest="download_quizzes",
        action="store_true",
        help="If specified, quizzes will be downloaded",
    )
    parser.add_argument(
        "--keep-vtt",
        dest="keep_vtt",
        action="store_true",
        help="If specified, .vtt files won't be removed",
    )
    parser.add_argument(
        "--skip-hls",
        dest="skip_hls",
        action="store_true",
        help="If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm lectures)",
    )
    parser.add_argument(
        "--info",
        dest="info",
        action="store_true",
        help="If specified, only course information will be printed, nothing will be downloaded",
    )
    parser.add_argument(
        "--id-as-course-name",
        dest="id_as_course_name",
        action="store_true",
        help="If specified, the course id will be used in place of the course name for the output directory. This is a 'hack' to reduce the path length",
    )
    parser.add_argument(
        "-sc",
        "--subscription-course",
        dest="is_subscription_course",
        action="store_true",
        help="Mark the course as a subscription based course, use this if you are having problems with the program auto detecting it",
    )
    parser.add_argument(
        "--save-to-file",
        dest="save_to_file",
        action="store_true",
        help="If specified, course content will be saved to a file that can be loaded later with --load-from-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--load-from-file",
        dest="load_from_file",
        action="store_true",
        help="If specified, course content will be loaded from a previously saved file with --save-to-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        type=str,
        help="Logging level: one of DEBUG, INFO, ERROR, WARNING, CRITICAL (Default is INFO)",
    )
    parser.add_argument(
        "--browser",
        dest="browser",
        help="The browser to extract cookies from",
        choices=["chrome", "firefox", "opera", "edge", "brave", "chromium", "vivaldi", "safari", "file"],
    )
    parser.add_argument(
        "--use-h265",
        dest="use_h265",
        action="store_true",
        help="If specified, videos will be encoded with the H.265 codec",
    )
    parser.add_argument(
        "--h265-crf",
        dest="h265_crf",
        type=int,
        default=28,
        help="Set a custom CRF value for H.265 encoding. FFMPEG default is 28",
    )
    parser.add_argument(
        "--h265-preset",
        dest="h265_preset",
        type=str,
        default="medium",
        help="Set a custom preset value for H.265 encoding. FFMPEG default is medium",
    )
    parser.add_argument(
        "--use-nvenc",
        dest="use_nvenc",
        action="store_true",
        help="Whether to use the NVIDIA hardware transcoding for H.265. Only works if you have a supported NVIDIA GPU and ffmpeg with nvenc support",
    )
    parser.add_argument(
        "--out",
        "-o",
        dest="out",
        type=str,
        help="Set the path to the output directory",
    )
    parser.add_argument(
        "--continue-lecture-numbers",
        "-n",
        dest="use_continuous_lecture_numbers",
        action="store_true",
        help="Use continuous lecture numbering instead of per-chapter",
    )
    parser.add_argument(
        "--chapter",
        dest="chapter_filter_raw",
        type=str,
        help="Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').",
    )
    parser.add_argument(
        "--lecture",
        dest="lecture_filter_raw",
        type=str,
        help="Download specific lectures within chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').",
    )
    # parser.add_argument("-v", "--version", action="version", version="You are running version {version}".format(version=__version__))

    args = parser.parse_args()
    if args.download_assets:
        dl_assets = True
    if args.lang:
        caption_locale = args.lang
    if args.download_captions:
        dl_captions = True
    if args.download_quizzes:
        dl_quizzes = True
    if args.skip_lectures:
        skip_lectures = True
    if args.quality:
        quality = args.quality
    if args.keep_vtt:
        keep_vtt = args.keep_vtt
    if args.skip_hls:
        skip_hls = args.skip_hls
    if args.concurrent_downloads:
        concurrent_downloads = args.concurrent_downloads

        if concurrent_downloads <= 0:
            # if the user gave a number that is less than or equal to 0, set cc to default of 10
            concurrent_downloads = 10
        elif concurrent_downloads > 30:
            # if the user gave a number thats greater than 30, set cc to the max of 30
            concurrent_downloads = 30
    if args.load_from_file:
        load_from_file = args.load_from_file
    if args.save_to_file:
        save_to_file = args.save_to_file
    if args.bearer_token:
        bearer_token = args.bearer_token
    if args.course_url:
        course_url = args.course_url
    if args.info:
        info = args.info
    if args.use_h265:
        use_h265 = True
    if args.h265_crf:
        h265_crf = args.h265_crf
    if args.h265_preset:
        h265_preset = args.h265_preset
    if args.use_nvenc:
        use_nvenc = True
    if args.log_level:
        if args.log_level.upper() == "DEBUG":
            LOG_LEVEL = logging.DEBUG
        elif args.log_level.upper() == "INFO":
            LOG_LEVEL = logging.INFO
        elif args.log_level.upper() == "ERROR":
            LOG_LEVEL = logging.ERROR
        elif args.log_level.upper() == "WARNING":
            LOG_LEVEL = logging.WARNING
        elif args.log_level.upper() == "CRITICAL":
            LOG_LEVEL = logging.CRITICAL
        else:
            print(f"Invalid log level: {args.log_level}; Using INFO")
            LOG_LEVEL = logging.INFO
    if args.id_as_course_name:
        id_as_course_name = args.id_as_course_name
    if args.is_subscription_course:
        is_subscription_course = args.is_subscription_course
    if args.browser:
        browser = args.browser
    if args.out:
        DOWNLOAD_DIR = os.path.abspath(args.out)
    if args.use_continuous_lecture_numbers:
        use_continuous_lecture_numbers = args.use_continuous_lecture_numbers

    # setup a logger
    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)

    # create a colored formatter for the console
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    # create a regular non-colored formatter for the log file
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # create a handler for console logging
    stream = logging.StreamHandler()
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)

    # create a handler for file logging
    file_handler = logging.FileHandler(LOG_FILE_PATH)
    file_handler.setFormatter(file_formatter)

    # construct the logger
    logger = logging.getLogger("udemy-downloader")
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(stream)
    logger.addHandler(file_handler)

    logger.info(f"Output directory set to {DOWNLOAD_DIR}")

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(SAVED_DIR).mkdir(parents=True, exist_ok=True)

    # Note: Decryption keys are now handled by the GUI interface

    # Process the chapter filter
    if args.chapter_filter_raw:
        chapter_filter = parse_chapter_filter(args.chapter_filter_raw)
        logger.info("Chapter filter applied: %s", sorted(chapter_filter))

    if args.lecture_filter_raw:
        lecture_filter = parse_lecture_filter(args.lecture_filter_raw)
        logger.info("Lecture filter applied: %s", sorted(lecture_filter))


class Udemy:
    def __init__(self, bearer_token):
        global cj

        self.session = None
        self.bearer_token = None
        self.auth = UdemyAuth(cache_session=False)
        if not self.session:
            self.session = self.auth.authenticate(bearer_token=bearer_token)

        if not self.session:
            if browser == None:
                logger.error("No bearer token was provided, and no browser for cookie extraction was specified.")
                sys.exit(1)

            logger.warning("No bearer token was provided, attempting to use browser cookies.")

            self.session = self.auth._session

            if browser == "chrome":
                cj = browser_cookie3.chrome()
            elif browser == "firefox":
                cj = browser_cookie3.firefox()
            elif browser == "opera":
                cj = browser_cookie3.opera()
            elif browser == "edge":
                cj = browser_cookie3.edge()
            elif browser == "brave":
                cj = browser_cookie3.brave()
            elif browser == "chromium":
                cj = browser_cookie3.chromium()
            elif browser == "vivaldi":
                cj = browser_cookie3.vivaldi()
            elif browser == "file":
                # load netscape cookies from file
                cj = MozillaCookieJar("cookies.txt")
                cj.load()

    def _get_quiz(self, quiz_id):
        self.session._headers.update(
            {
                "Host": "{portal_name}.udemy.com".format(portal_name=portal_name),
                "Referer": "https://{portal_name}.udemy.com/course/{course_name}/learn/quiz/{quiz_id}".format(
                    portal_name=portal_name, course_name=course_name, quiz_id=quiz_id
                ),
            }
        )
        url = QUIZ_URL.format(portal_name=portal_name, quiz_id=quiz_id)
        try:
            resp = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"[-] Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            return resp.get("results")

    def _get_elem_value_or_none(self, elem, key):
        return elem[key] if elem and key in elem else "(None)"

    def _get_quiz_with_info(self, quiz_id):
        resp = {"_class": None, "_type": None, "contents": None}
        quiz_json = self._get_quiz(quiz_id)
        is_only_one = len(quiz_json) == 1 and quiz_json[0]["_class"] == "assessment"
        is_coding_assignment = quiz_json[0]["assessment_type"] == "coding-problem"

        resp["_class"] = quiz_json[0]["_class"]

        if is_only_one and is_coding_assignment:
            assignment = quiz_json[0]
            prompt = assignment["prompt"]

            resp["_type"] = assignment["assessment_type"]

            resp["contents"] = {
                "instructions": self._get_elem_value_or_none(prompt, "instructions"),
                "tests": self._get_elem_value_or_none(prompt, "test_files"),
                "solutions": self._get_elem_value_or_none(prompt, "solution_files"),
            }

            resp["hasInstructions"] = False if resp["contents"]["instructions"] == "(None)" else True
            resp["hasTests"] = False if isinstance(resp["contents"]["tests"], str) else True
            resp["hasSolutions"] = False if isinstance(resp["contents"]["solutions"], str) else True
        else:  # Normal quiz
            resp["_type"] = "normal-quiz"
            resp["contents"] = quiz_json

        return resp

    def _extract_supplementary_assets(self, supp_assets, lecture_counter):
        _temp = []
        for entry in supp_assets:
            title = sanitize_filename(entry.get("title"))
            filename = entry.get("filename")
            download_urls = entry.get("download_urls")
            external_url = entry.get("external_url")
            asset_type = entry.get("asset_type").lower()
            id = entry.get("id")
            if asset_type == "file":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("File", [])[0].get("file")
                    _temp.append(
                        {
                            "type": "file",
                            "title": title,
                            "filename": "{0:03d} ".format(lecture_counter) + filename,
                            "extension": extension,
                            "download_url": download_url,
                            "id": id,
                        }
                    )
            elif asset_type == "sourcecode":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("SourceCode", [])[0].get("file")
                    _temp.append(
                        {
                            "type": "source_code",
                            "title": title,
                            "filename": "{0:03d} ".format(lecture_counter) + filename,
                            "extension": extension,
                            "download_url": download_url,
                            "id": id,
                        }
                    )
            elif asset_type == "externallink":
                _temp.append(
                    {
                        "type": "external_link",
                        "title": title,
                        "filename": "{0:03d} ".format(lecture_counter) + filename,
                        "extension": "txt",
                        "download_url": external_url,
                        "id": id,
                    }
                )
        return _temp

    def _extract_article(self, asset, id):
        return [
            {
                "type": "article",
                "body": asset.get("body"),
                "extension": "html",
                "id": id,
            }
        ]

    def _extract_ppt(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Presentation", [])[0].get("file")
            _temp.append(
                {
                    "type": "presentation",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_file(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("File", [])[0].get("file")
            _temp.append(
                {
                    "type": "file",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_ebook(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("E-Book", [])[0].get("file")
            _temp.append(
                {
                    "type": "ebook",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_audio(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Audio", [])[0].get("file")
            _temp.append(
                {
                    "type": "audio",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_sources(self, sources, skip_hls):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                label = source.get("label")
                download_url = source.get("file")
                if not download_url:
                    continue
                if label.lower() == "audio":
                    continue
                height = label if label else None
                if height == "2160":
                    width = "3840"
                elif height == "1440":
                    width = "2560"
                elif height == "1080":
                    width = "1920"
                elif height == "720":
                    width = "1280"
                elif height == "480":
                    width = "854"
                elif height == "360":
                    width = "640"
                elif height == "240":
                    width = "426"
                else:
                    width = "256"
                if source.get("type") == "application/x-mpegURL" or "m3u8" in download_url:
                    if not skip_hls:
                        out = self._extract_m3u8(download_url)
                        if out:
                            _temp.extend(out)
                else:
                    _type = source.get("type")
                    _temp.append(
                        {
                            "type": "video",
                            "height": height,
                            "width": width,
                            "extension": _type.replace("video/", ""),
                            "download_url": download_url,
                        }
                    )
        return _temp

    def _extract_media_sources(self, sources):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                _type = source.get("type")
                src = source.get("src")

                if _type == "application/dash+xml":
                    out = self._extract_mpd(src)
                    if out:
                        _temp.extend(out)
        return _temp

    def _extract_subtitles(self, tracks):
        _temp = []
        if tracks and isinstance(tracks, list):
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                if track.get("_class") != "caption":
                    continue
                download_url = track.get("url")
                if not download_url or not isinstance(download_url, str):
                    continue
                lang = (
                    track.get("language")
                    or track.get("srclang")
                    or track.get("label")
                    or track["locale_id"].split("_")[0]
                )
                ext = "vtt" if "vtt" in download_url.rsplit(".", 1)[-1] else "srt"
                _temp.append(
                    {
                        "type": "subtitle",
                        "language": lang,
                        "extension": ext,
                        "download_url": download_url,
                    }
                )
        return _temp

    def _extract_m3u8(self, url):
        """extracts m3u8 streams"""
        asset_id_re = re.compile(r"assets/(?P<id>\d+)/")
        _temp = []

        # get temp folder
        temp_path = Path(Path.cwd(), "temp")

        # ensure the folder exists
        temp_path.mkdir(parents=True, exist_ok=True)

        # # extract the asset id from the url
        asset_id = asset_id_re.search(url).group("id")

        m3u8_path = Path(temp_path, f"index_{asset_id}.m3u8")

        try:
            r = self.session._get(url)
            r.raise_for_status()
            raw_data = r.text

            # write to temp file for later
            with open(m3u8_path, "w") as f:
                f.write(r.text)

            m3u8_object = m3u8.loads(raw_data)
            playlists = m3u8_object.playlists
            seen = set()
            for pl in playlists:
                resolution = pl.stream_info.resolution
                codecs = pl.stream_info.codecs

                if not resolution:
                    continue
                if not codecs:
                    continue
                width, height = resolution

                if height in seen:
                    continue

                # we need to save the individual playlists to disk also
                playlist_path = Path(temp_path, f"index_{asset_id}_{width}x{height}.m3u8")

                with open(playlist_path, "w") as f:
                    r = self.session._get(pl.uri)
                    r.raise_for_status()
                    f.write(r.text)

                seen.add(height)
                _temp.append(
                    {
                        "type": "hls",
                        "height": height,
                        "width": width,
                        "extension": "mp4",
                        "download_url": playlist_path.as_uri(),
                    }
                )
        except Exception as error:
            logger.error(f"Udemy Says : '{error}' while fetching hls streams..")
        return _temp

    def _extract_mpd(self, url):
        """extracts mpd streams"""
        asset_id_re = re.compile(r"assets/(?P<id>\d+)/")
        _temp = []

        # get temp folder
        temp_path = Path(Path.cwd(), "temp")

        # ensure the folder exists
        temp_path.mkdir(parents=True, exist_ok=True)

        # # extract the asset id from the url
        asset_id = asset_id_re.search(url).group("id")

        # download the mpd and save it to the temp file
        mpd_path = Path(temp_path, f"index_{asset_id}.mpd")

        try:
            with open(mpd_path, "wb") as f:
                r = self.session._get(url)
                r.raise_for_status()
                f.write(r.content)

            ytdl = yt_dlp.YoutubeDL(
                {"quiet": True, "no_warnings": True, "allow_unplayable_formats": True, "enable_file_urls": True}
            )
            results = ytdl.extract_info(mpd_path.as_uri(), download=False, force_generic_extractor=True)
            format_id = results.get("format_id")
            extension = results.get("ext")
            height = results.get("height")
            width = results.get("width")

            _temp.append(
                {
                    "type": "dash",
                    "height": str(height),
                    "width": str(width),
                    "format_id": format_id.replace("+", ","),
                    "extension": extension,
                    "download_url": mpd_path.as_uri(),
                }
            )
        except Exception:
            logger.exception(f"Error fetching MPD streams")

        # We don't delete the mpd file yet because we can use it to download later
        return _temp

    def extract_course_name(self, url):
        """
        @author r0oth3x49
        """
        obj = re.search(
            r"(?i)(?://(?P<portal_name>.+?).udemy.com/(?:course(/draft)*/)?(?P<name_or_id>[a-zA-Z0-9_-]+))",
            url,
        )
        if obj:
            portal_name = obj.group("portal_name")
            # Normalize portal name - if it's 'www', treat as normal Udemy
            if portal_name == "www":
                portal_name = "www"
            return portal_name, obj.group("name_or_id")

    def extract_portal_name(self, url):
        obj = re.search(r"(?i)(?://(?P<portal_name>.+?).udemy.com)", url)
        if obj:
            return obj.group("portal_name")

    def _subscribed_courses(self, portal_name, course_name):
        results = []
        self.session._headers.update(
            {
                "Host": "{portal_name}.udemy.com".format(portal_name=portal_name),
                "Referer": "https://{portal_name}.udemy.com/home/my-courses/search/?q={course_name}".format(
                    portal_name=portal_name, course_name=course_name
                ),
            }
        )
        url = COURSE_SEARCH.format(portal_name=portal_name, course_name=course_name)
        try:
            webpage = self.session._get(url).content
            webpage = webpage.decode("utf8", "ignore")
            webpage = json.loads(webpage)
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"{error} on {url}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_info_json(self, url, course_id):
        self.session._headers.update({"Referer": url})
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        try:
            resp = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            return resp

    def _extract_course_curriculum(self, url, course_id, portal_name):
        self.session._headers.update({"Referer": url})
        url = CURRICULUM_ITEMS_URL.format(portal_name=portal_name, course_id=course_id)
        page = 1
        try:
            data = self.session._get(url, CURRICULUM_ITEMS_PARAMS).json()
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            _next = data.get("next")
            _count = data.get("count")
            est_page_count = math.ceil(_count / 100)  # 100 is the max results per page
            while _next:
                logger.info(f"> Downloading course curriculum.. (Page {page + 1}/{est_page_count})")
                try:
                    resp = self.session._get(_next)
                    if not resp.ok:
                        logger.error(f"Failed to fetch a page, will retry")
                        continue
                    resp = resp.json()
                except conn_error as error:
                    logger.fatal(f"Connection error: {error}")
                    time.sleep(0.8)
                    sys.exit(1)
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
                        page = page + 1
            return data

    def _extract_course(self, response, course_name):
        _temp = {}
        if response:
            for entry in response:
                course_id = str(entry.get("id"))
                published_title = entry.get("published_title")
                if course_name in (published_title, course_id):
                    _temp = entry
                    break
        return _temp

    def _my_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"{error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"{error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
            if results:
                [courses_lists.extend(courses.get("courses", [])) for courses in results if courses.get("courses", [])]
        return courses_lists

    def _archived_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            url = f"{url}&is_archived=true"
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"{error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_subscription_course_info(self, url):
        course_html = self.session._get(url).text
        soup = BeautifulSoup(course_html, "lxml")
        data = soup.find("div", {"class": "ud-component--course-taking--app"})
        if not data:
            logger.fatal(
                "Could not find course data. Possible causes are: Missing cookies.txt file, incorrect url (should end with /learn), not logged in to udemy in specified browser."
            )
            self.session.terminate()
            sys.exit(1)
        data_args = data.attrs["data-module-args"]
        data_json = json.loads(data_args)
        course_id = data_json.get("courseId", None)
        return course_id

    def _extract_course_info(self, url):
        global portal_name
        portal_name, course_name = self.extract_course_name(url)
        course = {"portal_name": portal_name}

        # Ensure session headers reflect the correct portal (normal or business)
        # Set default Host and Origin for subsequent requests; specific calls may override Referer as needed
        if portal_name:
            try:
                if portal_name == "www":
                    # Normal Udemy
                    self.session._headers.update(
                        {
                            "Host": "www.udemy.com",
                            "Origin": "https://www.udemy.com",
                        }
                    )
                else:
                    # Udemy Business/Enterprise portal
                    self.session._headers.update(
                        {
                            "Host": f"{portal_name}.udemy.com",
                            "Origin": f"https://{portal_name}.udemy.com",
                        }
                    )
            except Exception:
                pass

        if not is_subscription_course:
            results = self._subscribed_courses(portal_name=portal_name, course_name=course_name)
            course = self._extract_course(response=results, course_name=course_name)
            if not course:
                results = self._my_courses(portal_name=portal_name)
                course = self._extract_course(response=results, course_name=course_name)
            if not course:
                results = self._subscribed_collection_courses(portal_name=portal_name)
                course = self._extract_course(response=results, course_name=course_name)
            if not course:
                results = self._archived_courses(portal_name=portal_name)
                course = self._extract_course(response=results, course_name=course_name)

        if not course or is_subscription_course:
            course_id = self._extract_subscription_course_info(url)
            course = self._extract_course_info_json(url, course_id)

        if course:
            return course.get("id"), course
        if not course:
            logger.fatal("Downloading course information, course id not found .. ")
            logger.fatal(
                "It seems either you are not enrolled or you have to visit the course atleast once while you are logged in.",
            )
            logger.info(
                "Terminating Session...",
            )
            self.session.terminate()
            logger.info(
                "Session terminated.",
            )
            sys.exit(1)

    def _parse_lecture(self, lecture: dict):
        retVal = []

        index = lecture.get("index")  # this is lecture_counter
        lecture_data = lecture.get("data")
        asset = lecture_data.get("asset")
        supp_assets = lecture_data.get("supplementary_assets")

        if isinstance(asset, dict):
            asset_type = asset.get("asset_type").lower() or asset.get("assetType").lower()
            if asset_type == "article":
                retVal.extend(self._extract_article(asset, index))
            elif asset_type == "video":
                pass
            elif asset_type == "e-book":
                retVal.extend(self._extract_ebook(asset, index))
            elif asset_type == "file":
                retVal.extend(self._extract_file(asset, index))
            elif asset_type == "presentation":
                retVal.extend(self._extract_ppt(asset, index))
            elif asset_type == "audio":
                retVal.extend(self._extract_audio(asset, index))
            else:
                logger.warning(f"Unknown asset type: {asset_type}")

            if isinstance(supp_assets, list) and len(supp_assets) > 0:
                retVal.extend(self._extract_supplementary_assets(supp_assets, index))

        if asset != None:
            stream_urls = asset.get("stream_urls")
            if stream_urls != None:
                # not encrypted
                if stream_urls and isinstance(stream_urls, dict):
                    sources = stream_urls.get("Video")
                    tracks = asset.get("captions")
                    # duration = asset.get("time_estimation")
                    sources = self._extract_sources(sources, skip_hls)
                    subtitles = self._extract_subtitles(tracks)
                    sources_count = len(sources)
                    subtitle_count = len(subtitles)
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "sources": sources,
                        "subtitles": subtitles,
                        "subtitle_count": subtitle_count,
                        "sources_count": sources_count,
                        "is_encrypted": False,
                        "asset_id": asset.get("id"),
                        "type": asset.get("asset_type"),
                    }
                else:
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        "html_content": asset.get("body"),
                        "extension": "html",
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "subtitle_count": 0,
                        "sources_count": 0,
                        "is_encrypted": False,
                        "asset_id": asset.get("id"),
                        "type": asset.get("asset_type"),
                    }
            else:
                # encrypted
                media_sources = asset.get("media_sources")
                if media_sources and isinstance(media_sources, list):
                    sources = self._extract_media_sources(media_sources)
                    tracks = asset.get("captions")
                    # duration = asset.get("time_estimation")
                    subtitles = self._extract_subtitles(tracks)
                    sources_count = len(sources)
                    subtitle_count = len(subtitles)
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        # "duration": duration,
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "video_sources": sources,
                        "subtitles": subtitles,
                        "subtitle_count": subtitle_count,
                        "sources_count": sources_count,
                        "is_encrypted": True,
                        "asset_id": asset.get("id"),
                        "type": asset.get("asset_type"),
                    }

                else:
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        "html_content": asset.get("body"),
                        "extension": "html",
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "subtitle_count": 0,
                        "sources_count": 0,
                        "is_encrypted": False,
                        "asset_id": asset.get("id"),
                        "type": asset.get("asset_type"),
                    }
        else:
            lecture = {
                **lecture,
                "assets": retVal,
                "assets_count": len(retVal),
                "asset_id": lecture_data.get("id"),
                "type": lecture_data.get("type"),
            }

        return lecture


class Session(object):
    def __init__(self):
        self._headers = HEADERS
        self._session = requests.sessions.Session()
        self._session.mount(
            "https://",
            SSLCiphers(
                cipher_list="ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256:AES256-SH"
            ),
        )

    def _set_auth_headers(self, bearer_token=""):
        self._headers["Authorization"] = "Bearer {}".format(bearer_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(bearer_token)

    def _get(self, url, params=None):
        for i in range(10):
            session = self._session.get(url, headers=self._headers, cookies=cj, params=params)
            if session.ok or session.status_code in [502, 503]:
                return session
            if not session.ok:
                logger.error("Failed request " + url)
                logger.error(f"{session.status_code} {session.reason}, retrying (attempt {i} )...")
                time.sleep(0.8)

    def _post(self, url, data, redirect=True):
        session = self._session.post(url, data, headers=self._headers, allow_redirects=redirect, cookies=cj)
        if session.ok:
            return session
        if not session.ok:
            raise Exception(f"{session.status_code} {session.reason}")

    def terminate(self):
        self._set_auth_headers()
        return


class UdemyAuth(object):
    def __init__(self, username="", password="", cache_session=False):
        self.username = username
        self.password = password
        self._cache = cache_session
        self._session = Session()

    def authenticate(self, bearer_token=None):
        if bearer_token:
            self._session._set_auth_headers(bearer_token=bearer_token)
            return self._session
        else:
            return None


def durationtoseconds(period):
    """
    @author Jayapraveen
    """

    # Duration format in PTxDxHxMxS
    if period[:2] == "PT":
        period = period[2:]
        day = int(period.split("D")[0] if "D" in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if "H" in period else 0)
        minute = int(period.split("M")[0].split("H")[-1] if "M" in period else 0)
        second = period.split("S")[0].split("M")[-1]
        # logger.debug("Total time: " + str(day) + " days " + str(hour) + " hours " +
        #       str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(
            str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) + (int(second.split(".")[0])))
            + "."
            + str(int(second.split(".")[-1]))
        )
        return total_time

    else:
        logger.error("Duration Format Error")
        return None


def mux_process(video_filepath: str, audio_filepath: str, video_title: str, output_path: str):
    codec = "hevc_nvenc" if use_nvenc else "libx265"
    transcode = "-hwaccel cuda -hwaccel_output_format cuda" if use_nvenc else ""
    
    ffmpeg_path = find_executable("ffmpeg")
    if not ffmpeg_path:
        logger.fatal("FFMPEG executable not found. Video muxing cannot proceed.")
        sys.exit(1)

    if os.name == "nt":
        if use_h265:
            command = f'\"{ffmpeg_path}\" {transcode} -y -i \"{video_filepath}\" -i \"{audio_filepath}\" -c:v {codec} -vtag hvc1 -crf {h265_crf} -preset {h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title=\"{video_title}\" \"{output_path}\"'
        else:
            command = f'\"{ffmpeg_path}\" -y -i \"{video_filepath}\" -i \"{audio_filepath}\" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title=\"{video_title}\" \"{output_path}\"'
    else:
        if use_h265:
            command = f'nice -n 7 \"{ffmpeg_path}\" {transcode} -y -i \"{video_filepath}\" -i \"{audio_filepath}\" -c:v {codec} -vtag hvc1 -crf {h265_crf} -preset {h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title=\"{video_title}\" \"{output_path}\"'
        else:
            command = f'nice -n 7 \"{ffmpeg_path}\" -y -i \"{video_filepath}\" -i \"{audio_filepath}\" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title=\"{video_title}\" \"{output_path}\"'
  
    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("FFMPEG-STDOUT", process.stdout)
    log_subprocess_output("FFMPEG-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Muxing returned a non-zero exit code")


def handle_segments(url, format_id, lecture_id, chapter_dir):
    os.chdir(os.path.join(chapter_dir))

    video_filepath_enc = lecture_id + ".encrypted.mp4"
    audio_filepath_enc = lecture_id + ".encrypted.m4a"

    logger.info("> Downloading Lecture Tracks...")
    aria2c_path = find_executable("aria2c")
    if not aria2c_path:
        logger.fatal("aria2c executable not found. Segment downloading cannot proceed.")
        sys.exit(1)
    args = [
        aria2c_path,
        "--enable-file-urls",
        "--force-generic-extractor",
        "--allow-unplayable-formats",
        "--concurrent-fragments",
        f"{concurrent_downloads}",
        "--downloader",
        aria2c_path,
        "--downloader-args",
        'aria2c:"--disable-ipv6"',
        "--fixup",
        "never",
        "-k",
        "-o",
        f"{lecture_id}.encrypted.%(ext)s",
        "-f",
        format_id,
        f"{url}",
    ]
    process = subprocess.Popen(args)
    log_subprocess_output("ARIA2-STDOUT", process.stdout)
    log_subprocess_output("ARIA2-STDERR", process.stderr)
    ret_code = process.wait()
    logger.info("> Lecture Tracks Downloaded")

    if ret_code != 0:
        logger.warning("Return code from the downloader was non-0 (error), skipping!")
        return

    # No decryption or muxing here, just download the encrypted files.
    # The KIDs and keys are no longer needed here.
    # Decryption and combining will be handled by gui.py's functions.

    os.chdir(HOME_DIR)
    # if the url is a file url, we need to remove the file after we're done with it
    if url.startswith("file://"):
        try:
            os.unlink(url[7:])
        except:
            pass
    return # No return code needed here as we are not decrypting/muxing


def check_for_aria():
    try:
        aria2c_path = find_executable("aria2c")
        if not aria2c_path:
            return False
        subprocess.Popen([aria2c_path, "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for aria2c, please tell the program author about this! "
        )
        return True


def check_for_ffmpeg():
    try:
        ffmpeg_path = find_executable("ffmpeg")
        if not ffmpeg_path:
            return False
        subprocess.Popen([ffmpeg_path], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for FFMPEG, please tell the program author about this! "
        )
        return True


def check_for_shaka():
    try:
        subprocess.Popen(["shaka-packager", "-version"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for shaka-packager, please tell the program author about this! "
        )
        return True


def download(url, path, filename):
    """
    @author Puyodead1
    """
    file_size = int(requests.head(url).headers["Content-Length"])
    if os.path.exists(path):
        first_byte = os.path.getsize(path)
    else:
        first_byte = 0
    if first_byte >= file_size:
        return file_size
    header = {"Range": "bytes=%s-%s" % (first_byte, file_size)}
    pbar = tqdm(total=file_size, initial=first_byte, unit="B", unit_scale=True, desc=filename)
    res = requests.get(url, headers=header, stream=True)
    res.raise_for_status()
    with open(path, encoding="utf8", mode="ab") as f:
        for chunk in res.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                pbar.update(1024)
    pbar.close()
    return file_size


def download_aria(url, file_dir, filename):
    """
    @author Puyodead1
    """
    aria2c_path = find_executable("aria2c")
    if not aria2c_path:
        logger.fatal("aria2c executable not found. File downloading cannot proceed.")
        sys.exit(1)

    args = [
        aria2c_path,
        url,
        "-o",
        filename,
        "-d",
        file_dir,
        "-j16",
        "-s20",
        "-x16",
        "-c",
        "--auto-file-renaming=false",
        "--summary-interval=0",
        "--disable-ipv6",
        "--follow-torrent=false",
    ]
    process = subprocess.Popen(args)
    log_subprocess_output("ARIA2-STDOUT", process.stdout)
    log_subprocess_output("ARIA2-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Return code from the downloader was non-0 (error)")
    return ret_code


def process_caption(caption, lecture_id, lecture_title, lecture_dir, tries=0):
    # Use lecture_title for naming captions to align with video naming
    sanitized_lecture_title = sanitize_filename(lecture_title)
    filename = f"%s_%s.%s" % (sanitized_lecture_title, caption.get("language"), caption.get("extension"))
    filename_no_ext = f"%s_%s" % (sanitized_lecture_title, caption.get("language"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        logger.info("    > Caption '%s' already downloaded." % filename)
    else:
        logger.info(f"    >  Downloading caption: '%s'" % filename)
        try:
            ret_code = download_aria(caption.get("download_url"), lecture_dir, filename)
            logger.debug(f"      > Download return code: {ret_code}")
        except Exception as e:
            error_message = str(e)
            if "status=403" in error_message or "Forbidden" in error_message:
                logger.error(f"    > Error downloading caption: {e}. Access denied (403 Forbidden), skipping further retries.")
                return
            elif tries >= 3:
                logger.error(f"    > Error downloading caption: {e}. Exceeded retries, skipping.")
                return
            else:
                logger.error(f"    > Error downloading caption: {e}. Will retry {3-tries} more times.")
                process_caption(caption, lecture_id, lecture_title, lecture_dir, tries + 1)
        if caption.get("extension") == "vtt":
            try:
                logger.info("    > Converting caption to SRT format...")
                convert(lecture_dir, filename_no_ext)
                logger.info("    > Caption conversion complete.")
                if not keep_vtt:
                    os.remove(filepath)
            except Exception:
                logger.exception(f"    > Error converting caption")


def process_lecture(lecture, lecture_path, chapter_dir):
    lecture_id = lecture.get("id")
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_sources = lecture.get("video_sources")

    if is_encrypted:
        if len(lecture_sources) > 0:
            source = lecture_sources[-1]  # last index is the best quality
            if isinstance(quality, int):
                source = min(lecture_sources, key=lambda x: abs(int(x.get("height")) - quality))
            logger.info(f"      > Lecture '{lecture_title}' has DRM, attempting to download")
            handle_segments(
                source.get("download_url"),
                source.get("format_id"),
                str(lecture_id),
                chapter_dir,
            )
        else:
            logger.info(f"      > Lecture '{lecture_title}' is missing media links")
            logger.debug(f"Lecture source count: {len(lecture_sources)}")
    else:
        sources = lecture.get("sources")
        sources = sorted(sources, key=lambda x: int(x.get("height")), reverse=True)
        if sources:
            if not os.path.isfile(lecture_path):
                logger.info("      > Lecture doesn't have DRM, attempting to download...")
                source = sources[0]  # first index is the best quality
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get("height")) - quality))
                try:
                    logger.info("      ====== Selected quality: %s %s", source.get("type"), source.get("height"))
                    url = source.get("download_url")
                    source_type = source.get("type")
                    if source_type == "hls":
                        temp_filepath = lecture_path.replace(".mp4", ".%(ext)s")
                        cmd = [
                            "yt-dlp",
                            "--enable-file-urls",
                            "--force-generic-extractor",
                            "--concurrent-fragments",
                            f"{concurrent_downloads}",
                            "--downloader",
                            "aria2c",
                            "--downloader-args",
                            'aria2c:"--disable-ipv6"',
                            "-o",
                            f"{temp_filepath}",
                            f"{url}",
                        ]
                        process = subprocess.Popen(cmd)
                        log_subprocess_output("YTDLP-STDOUT", process.stdout)
                        log_subprocess_output("YTDLP-STDERR", process.stderr)
                        ret_code = process.wait()
                        if ret_code == 0:
                            tmp_file_path = lecture_path + ".tmp"
                            logger.info("      > HLS Download success")
                            if use_h265:
                                codec = "hevc_nvenc" if use_nvenc else "libx265"
                                transcode = "-hwaccel cuda -hwaccel_output_format cuda".split(" ") if use_nvenc else []
                                cmd = [
                                    "ffmpeg",
                                    *transcode,
                                    "-y",
                                    "-i",
                                    lecture_path,
                                    "-c:v",
                                    codec,
                                    "-c:a",
                                    "copy",
                                    "-f",
                                    "mp4",
                                    tmp_file_path,
                                ]
                                process = subprocess.Popen(cmd)
                                log_subprocess_output("FFMPEG-STDOUT", process.stdout)
                                log_subprocess_output("FFMPEG-STDERR", process.stderr)
                                ret_code = process.wait()
                                if ret_code == 0:
                                    os.unlink(lecture_path)
                                    os.rename(tmp_file_path, lecture_path)
                                    logger.info("      > Encoding complete")
                                else:
                                    logger.error("      > Encoding returned non-zero return code")
                    else:
                        ret_code = download_aria(url, chapter_dir, lecture_title + ".mp4")
                        logger.debug(f"      > Download return code: {ret_code}")
                except Exception:
                    logger.exception(f">        Error downloading lecture")
            else:
                logger.info(f"      > Lecture '{lecture_title}' is already downloaded, skipping...")
        else:
            logger.error("      > Missing sources for lecture", lecture)


def process_quiz(udemy: Udemy, lecture, chapter_dir):
    quiz = udemy._get_quiz_with_info(lecture.get("id"))
    if quiz["_type"] == "coding-problem":
        process_coding_assignment(quiz, lecture, chapter_dir)
    else:  # Normal quiz
        process_normal_quiz(quiz, lecture, chapter_dir)


def process_normal_quiz(quiz, lecture, chapter_dir):
    lecture_title = lecture.get("lecture_title")
    lecture_index = lecture.get("lecture_index")
    lecture_file_name = sanitize_filename(lecture_title + ".html")
    lecture_path = os.path.join(chapter_dir, lecture_file_name)

    logger.info(f"  > Processing quiz {lecture_index}")
    with open("./templates/quiz_template.html", "r") as f:
        html = f.read()
        quiz_data = {
            "quiz_id": lecture["data"].get("id"),
            "quiz_description": lecture["data"].get("description"),
            "quiz_title": lecture["data"].get("title"),
            "pass_percent": lecture.get("data").get("pass_percent"),
            "questions": quiz["contents"],
        }
        html = html.replace("__data_placeholder__", json.dumps(quiz_data))
        with open(lecture_path, "w") as f:
            f.write(html)


def process_coding_assignment(quiz, lecture, chapter_dir):
    lecture_title = lecture.get("lecture_title")
    lecture_index = lecture.get("lecture_index")
    lecture_file_name = sanitize_filename(lecture_title + ".html")
    lecture_path = os.path.join(chapter_dir, lecture_file_name)

    logger.info(f"  > Processing quiz {lecture_index} (coding assignment)")

    with open("./templates/coding_assignment_template.html", "r") as f:
        html = f.read()
        quiz_data = {
            "title": lecture_title,
            "hasInstructions": quiz["hasInstructions"],
            "hasTests": quiz["hasTests"],
            "hasSolutions": quiz["hasSolutions"],
            "instructions": quiz["contents"]["instructions"],
            "tests": quiz["contents"]["tests"],
            "solutions": quiz["contents"]["solutions"],
        }
        html = html.replace("__data_placeholder__", json.dumps(quiz_data))
        with open(lecture_path, "w") as f:
            f.write(html)


def parse_new(udemy: Udemy, udemy_object: dict):
    # Prepare chapters/videos structure for selection GUI
    chapters_for_gui = []
    for chapter in udemy_object.get("chapters", []):
        chapter_dict = {
            "id": chapter.get("chapter_index"),
            "title": chapter.get("chapter_title"),
            "videos": []
        }
        for lecture in chapter.get("lectures", []):
            # Only add video lectures
            if lecture.get("_class") == "lecture":
                # Try to get thumbnail if available (add logic if you have thumbnail URLs)
                thumb_url = lecture.get("data", {}).get("asset", {}).get("thumbnail_url")
                chapter_dict["videos"].append({
                    "id": lecture.get("id"),
                    "title": lecture.get("lecture_title"),
                    "thumbnail_url": thumb_url
                })
        chapters_for_gui.append(chapter_dict)

    course_name = str(udemy_object.get("course_id")) if id_as_course_name else udemy_object.get("course_title")
    course_dir = os.path.join(DOWNLOAD_DIR, sanitize_filename(course_name))
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)

    # Create and save lecture ID to title mapping
    id_to_title_map = {}
    for chapter in udemy_object.get("chapters", []):
        for lecture in chapter.get("lectures", []):
            lecture_id = str(lecture.get("id"))
            lecture_title = lecture.get("lecture_title")
            if lecture_id and lecture_title:
                id_to_title_map[lecture_id] = lecture_title

    # Show selection window and get user selection
    selected_pairs = show_video_selection_window(chapters_for_gui, course_out_dir=course_dir, id_to_title_map=id_to_title_map)
    # selected_pairs is a list of (chapter_id, video_id)
    selected_video_ids = set(vid for chap, vid in selected_pairs)
    total_chapters = udemy_object.get("total_chapters")
    total_lectures = udemy_object.get("total_lectures")
    logger.info(f"Chapter(s) ({total_chapters})")
    logger.info(f"Lecture(s) ({total_lectures})")
    print(f"GUI_PROGRESS:TOTAL_LECTURES:{total_lectures}", flush=True) # Report total lectures for GUI
    
    if id_to_title_map:
        map_file_path = os.path.join(course_dir, "id_to_title.json")
        try:
            with open(map_file_path, "w", encoding="utf-8") as f:
                json.dump(id_to_title_map, f, indent=2, ensure_ascii=False)
            logger.info(f"> Saved lecture ID to title mapping at {map_file_path}")
        except Exception as e:
            logger.error(f"> Error saving ID to title mapping: {e}")

    for chapter in udemy_object.get("chapters"):
        current_chapter_index = int(chapter.get("chapter_index"))
        # Skip chapters not in the filter if a filter is provided
        if chapter_filter is not None and current_chapter_index not in chapter_filter:
            logger.info("Skipping chapter %s as it is not in the specified filter", current_chapter_index)
            continue

        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)
        logger.info(f"======= Processing chapter {chapter_index} of {total_chapters} =======")

        for lecture in chapter.get("lectures"):
            # Only process if selected by user
            if lecture.get("id") not in selected_video_ids:
                continue
            current_lecture_index = int(lecture.get("index"))
            # Skip lectures not in the filter if a filter is provided
            if lecture_filter is not None and current_lecture_index not in lecture_filter:
                logger.info("Skipping lecture %s as it is not in the specified filter", current_lecture_index)
                continue

            clazz = lecture.get("_class")

            if clazz == "quiz":
                # skip the quiz if we dont want to download it
                if not dl_quizzes:
                    continue
                process_quiz(udemy, lecture, chapter_dir)
                continue

            index = lecture.get("index")  # this is lecture_counter
            # lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy

            lecture_title = lecture.get("lecture_title")
            parsed_lecture = udemy._parse_lecture(lecture)

            lecture_extension = parsed_lecture.get("extension")
            extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
            if lecture_extension != None:
                # if the lecture extension property isnt none, set the extension to the lecture extension
                extension = lecture_extension
            lecture_file_name = sanitize_filename(lecture_title + "." + extension)
            lecture_file_name = deEmojify(lecture_file_name)
            lecture_path = os.path.join(chapter_dir, lecture_file_name)

            if not skip_lectures:
                logger.info(f"  > Processing lecture {index} of {total_lectures}")
                # Report current lecture progress for GUI
                print(f"GUI_PROGRESS:COMPLETED_LECTURE:{index}", flush=True)

                # Check if the lecture is already downloaded
                if os.path.isfile(lecture_path):
                    logger.info("      > Lecture '%s' is already downloaded, skipping..." % lecture_title)
                else:
                    # Check if the file is an html file
                    if extension == "html":
                        # if the html content is None or an empty string, skip it so we dont save empty html files
                        if parsed_lecture.get("html_content") != None and parsed_lecture.get("html_content") != "":
                            html_content = parsed_lecture.get("html_content").encode("utf8", "ignore").decode("utf8")
                            lecture_path = os.path.join(chapter_dir, "{}.html".format(sanitize_filename(lecture_title)))
                            try:
                                with open(lecture_path, encoding="utf8", mode="w") as f:
                                    f.write(html_content)
                            except Exception:
                                logger.exception("    > Failed to write html file")
                    else:
                        process_lecture(parsed_lecture, lecture_path, chapter_dir)

            # download subtitles for this lecture
            subtitles = parsed_lecture.get("subtitles")
            if dl_captions and subtitles != None and lecture_extension == None:
                logger.info("Processing {} caption(s)...".format(len(subtitles)))
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if lang == caption_locale or caption_locale == "all":
                        process_caption(subtitle, parsed_lecture.get("id"), lecture_title, chapter_dir)

            if dl_assets:
                assets = parsed_lecture.get("assets")
                logger.info("    > Processing {} asset(s) for lecture...".format(len(assets)))

                for asset in assets:
                    asset_type = asset.get("type")
                    filename = asset.get("filename")
                    download_url = asset.get("download_url")

                    if asset_type == "article":
                        body = asset.get("body")
                        # stip the 03d prefix
                        lecture_path = os.path.join(chapter_dir, "{}.html".format(sanitize_filename(lecture_title)))
                        try:
                            with open("./templates/article_template.html", "r") as f:
                                content = f.read()
                                content = content.replace("__title_placeholder__", lecture_title[4:])
                                content = content.replace("__data_placeholder__", body)
                                with open(lecture_path, encoding="utf8", mode="w") as f:
                                    f.write(content)
                        except Exception as e:
                            print("Failed to write html file: ", e)
                            continue
                    elif asset_type == "video":
                        logger.warning(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        logger.warning("AssetType: Video; AssetData: ", asset)
                    elif (
                        asset_type == "audio"
                        or asset_type == "e-book"
                        or asset_type == "file"
                        or asset_type == "presentation"
                        or asset_type == "ebook"
                        or asset_type == "source_code"
                    ):
                        try:
                            ret_code = download_aria(download_url, chapter_dir, filename)
                            logger.debug(f"      > Download return code: {ret_code}")
                        except Exception:
                            logger.exception("> Error downloading asset")
                    elif asset_type == "external_link":
                        # write the external link to a shortcut file
                        file_path = os.path.join(chapter_dir, f"{filename}.url")
                        file = open(file_path, "w")
                        file.write("[InternetShortcut]\n")
                        file.write(f"URL={download_url}")
                        file.close()

                        # save all the external links to a single file
                        savedirs, name = os.path.split(os.path.join(chapter_dir, filename))
                        filename = "external-links.txt"
                        filename = os.path.join(savedirs, filename)
                        file_data = []
                        if os.path.isfile(filename):
                            file_data = [
                                i.strip().lower() for i in open(filename, encoding="utf-8", errors="ignore") if i
                            ]

                        content = "\n{}\n{}\n".format(name, download_url)
                        if name.lower() not in file_data:
                            with open(filename, "a", encoding="utf-8", errors="ignore") as f:
                                f.write(content)


def _print_course_info(udemy: Udemy, udemy_object: dict):
    course_title = udemy_object.get("title")
    chapter_count = udemy_object.get("total_chapters")
    lecture_count = udemy_object.get("total_lectures")

    if lecture_count > 100:
        logger.warning(
            "This course has a lot of lectures! Fetching all the information can take a long time as well as spams Udemy's servers. It is NOT recommended to continue! Are you sure you want to do this?"
        )
        yn = input("(y/n): ")
        if yn.lower() != "y":
            logger.info("Probably wise. Please remove the --info argument and try again.")
            sys.exit(0)

    logger.info("> Course: {}".format(course_title))
    logger.info("> Total Chapters: {}".format(chapter_count))
    logger.info("> Total Lectures: {}".format(lecture_count))
    logger.info("\n")

    chapters = udemy_object.get("chapters")
    for chapter in chapters:
        current_chapter_index = int(chapter.get("chapter_index"))
        # Skip chapters not in the filter if a filter is provided
        if chapter_filter is not None and current_chapter_index not in chapter_filter:
            continue

        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_lecture_count = chapter.get("lecture_count")
        chapter_lectures = chapter.get("lectures")

        logger.info("> Chapter: {} ({} of {})".format(chapter_title, chapter_index, chapter_count))

        for lecture in chapter_lectures:
            current_lecture_index = int(lecture.get("index"))
            if lecture_filter is not None and current_lecture_index not in lecture_filter:
                continue

            lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy
            lecture_title = lecture.get("lecture_title")
            parsed_lecture = udemy._parse_lecture(lecture)

            lecture_sources = parsed_lecture.get("sources")
            lecture_is_encrypted = parsed_lecture.get("is_encrypted", None)
            lecture_extension = parsed_lecture.get("extension")
            lecture_asset_count = parsed_lecture.get("assets_count")
            lecture_subtitles = parsed_lecture.get("subtitles")
            lecture_video_sources = parsed_lecture.get("video_sources")
            lecture_type = parsed_lecture.get("type")

            lecture_qualities = []

            if lecture_sources:
                lecture_sources = sorted(lecture_sources, key=lambda x: int(x.get("height")), reverse=True)
            if lecture_video_sources:
                lecture_video_sources = sorted(lecture_video_sources, key=lambda x: int(x.get("height")), reverse=True)

            if lecture_is_encrypted and lecture_video_sources != None:
                lecture_qualities = [
                    "{}@{}x{}".format(x.get("type"), x.get("width"), x.get("height")) for x in lecture_video_sources
                ]
            elif lecture_is_encrypted == False and lecture_sources != None:
                lecture_qualities = [
                    "{}@{}x{}".format(x.get("type"), x.get("height"), x.get("width")) for x in lecture_sources
                ]

            if lecture_extension:
                continue

            logger.info("  > Lecture: {} ({} of {})".format(lecture_title, lecture_index, chapter_lecture_count))
            logger.info("    > Type: {}".format(lecture_type))
            if lecture_is_encrypted != None:
                logger.info("    > DRM: {}".format(lecture_is_encrypted))
            if lecture_asset_count:
                logger.info("    > Asset Count: {}".format(lecture_asset_count))
            if lecture_subtitles:
                logger.info("    > Captions: {}".format(", ".join([x.get("language") for x in lecture_subtitles])))
            if lecture_qualities:
                logger.info("    > Qualities: {}".format(lecture_qualities))

        if chapter_index != chapter_count:
            logger.info("==========================================")


def main():
    global bearer_token, portal_name
    aria_ret_val = check_for_aria()
    if not aria_ret_val:
        logger.warning("> aria2c is missing from your system or path! Some downloads may not work.")
        logger.warning("> Please install aria2c from: https://github.com/aria2/aria2/")

    ffmpeg_ret_val = check_for_ffmpeg()
    if not ffmpeg_ret_val and not skip_lectures:
        logger.warning("> FFMPEG is missing from your system or path! Video processing may not work.")
        logger.warning("> Please install ffmpeg from: https://www.ffmpeg.org/")

    shaka_ret_val = check_for_shaka()
    if not shaka_ret_val and not skip_lectures:
        logger.warning("> Shaka Packager is missing from your system or path! DRM decryption may not work.")
        logger.warning("> Please install shaka-packager from: https://github.com/shaka-project/shaka-packager/releases/latest")

    if load_from_file:
        logger.info("> 'load_from_file' was specified, data will be loaded from json files instead of fetched")
    if save_to_file:
        logger.info("> 'save_to_file' was specified, data will be saved to json files")

    load_dotenv()
    if bearer_token:
        bearer_token = bearer_token
    else:
        bearer_token = os.getenv("UDEMY_BEARER")

    udemy = Udemy(bearer_token)

    logger.info("> Fetching course information, this may take a minute...")
    if not load_from_file:
        course_id, course_info = udemy._extract_course_info(course_url)
        logger.info("> Course information retrieved!")
        if course_info and isinstance(course_info, dict):
            title = sanitize_filename(course_info.get("title"))
            course_title = course_info.get("published_title")

    logger.info("> Fetching course curriculum, this may take a minute...")
    if load_from_file:
        course_json = json.loads(
            open(os.path.join(os.getcwd(), "saved", "course_content.json"), encoding="utf8", mode="r").read()
        )
        title = course_json.get("title")
        course_title = course_json.get("published_title")
        portal_name = course_json.get("portal_name")
    else:
        course_json = udemy._extract_course_curriculum(course_url, course_id, portal_name)
        course_json["portal_name"] = portal_name

    if save_to_file:
        with open(os.path.join(os.getcwd(), "saved", "course_content.json"), encoding="utf8", mode="w") as f:
            f.write(json.dumps(course_json))

    logger.info("> Course curriculum retrieved!")
    course = course_json.get("results")
    resource = course_json.get("detail")

    if load_from_file:
        udemy_object = json.loads(
            open(os.path.join(os.getcwd(), "saved", "_udemy.json"), encoding="utf8", mode="r").read()
        )
        if info:
            _print_course_info(udemy, udemy_object)
        else:
            parse_new(udemy, udemy_object)
    else:
        udemy_object = {}
        udemy_object["bearer_token"] = bearer_token
        udemy_object["course_id"] = course_id
        udemy_object["title"] = title
        udemy_object["course_title"] = course_title
        udemy_object["chapters"] = []
        chapter_index_counter = -1

        if resource:
            logger.info("> Terminating Session...")
            udemy.session.terminate()
            logger.info("> Session Terminated.")

        if course:
            logger.info("> Processing course data, this may take a minute. ")
            lecture_counter = 0
            lectures = []

            for entry in course:
                clazz = entry.get("_class")

                if clazz == "chapter":
                    # reset lecture tracking
                    if not use_continuous_lecture_numbers:
                        lecture_counter = 0
                    lectures = []

                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))

                    if chapter_title not in udemy_object["chapters"]:
                        udemy_object["chapters"].append(
                            {
                                "chapter_title": chapter_title,
                                "chapter_id": entry.get("id"),
                                "chapter_index": chapter_index,
                                "lectures": [],
                            }
                        )
                        chapter_index_counter += 1
                elif clazz == "lecture":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(udemy_object["chapters"]) == 0:
                        # dummy chapters to handle lectures without chapters
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in udemy_object["chapters"]:
                            udemy_object["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            chapter_index_counter += 1
                    if lecture_id:
                        logger.info(f"Processing {course.index(entry) + 1} of {len(course)}")

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        lectures.append(
                            {
                                "index": lecture_counter,
                                "lecture_index": lecture_index,
                                "lecture_title": lecture_title,
                                "_class": entry.get("_class"),
                                "id": lecture_id,
                                "data": entry,
                            }
                        )
                    else:
                        logger.debug("Lecture: ID is None, skipping")
                elif clazz == "quiz":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(udemy_object["chapters"]) == 0:
                        # dummy chapters to handle lectures without chapters
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in udemy_object["chapters"]:
                            udemy_object["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            chapter_index_counter += 1

                    if lecture_id:
                        logger.info(f"Processing {course.index(entry) + 1} of {len(course)}")

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        lectures.append(
                            {
                                "index": lecture_counter,
                                "lecture_index": lecture_index,
                                "lecture_title": lecture_title,
                                "_class": entry.get("_class"),
                                "id": lecture_id,
                                "data": entry,
                            }
                        )
                    else:
                        logger.debug("Quiz: ID is None, skipping")

                udemy_object["chapters"][chapter_index_counter]["lectures"] = lectures
                udemy_object["chapters"][chapter_index_counter]["lecture_count"] = len(lectures)

            udemy_object["total_chapters"] = len(udemy_object["chapters"])
            udemy_object["total_lectures"] = sum(
                [entry.get("lecture_count", 0) for entry in udemy_object["chapters"] if entry]
            )

        if save_to_file:
            with open(os.path.join(os.getcwd(), "saved", "_udemy.json"), encoding="utf8", mode="w") as f:
                # remove "bearer_token" from the object before writing
                udemy_object.pop("bearer_token")
                udemy_object["portal_name"] = portal_name
                f.write(json.dumps(udemy_object))
            logger.info("> Saved parsed data to json")

        if info:
            _print_course_info(udemy, udemy_object)
        else:
            parse_new(udemy, udemy_object)


if __name__ == "__main__":
    # pre run parses arguments, sets up logging, and creates directories
    pre_run()
    # run main program
    main()
