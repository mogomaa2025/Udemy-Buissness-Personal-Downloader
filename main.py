from selection_window import show_video_selection_window

# -*- coding: utf-8 -*-
import argparse
import io
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
from typing import IO, Union, Dict, List

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
def _configure_utf8_streams():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if not stream:
            continue
        try:
            if getattr(stream, "encoding", "").lower() == "utf-8":
                continue
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                buffer = getattr(stream, "buffer", None)
                if buffer:
                    wrapper = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")
                    setattr(sys, name, wrapper)
        except Exception:
            continue


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
        "--no-report",
        dest="no_report",
        action="store_true",
        help="Disable automatic verification report generation and opening",
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

    _configure_utf8_streams()

    # setup a logger
    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)

    # create a colored formatter for the console
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    # create a regular non-colored formatter for the log file
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # create a handler for console logging
    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)

    # create a handler for file logging
    file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
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

    return args


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
        max_page_retries = 5
        
        try:
            logger.info("> Fetching initial course curriculum page...")
            data = self.session._get(url, CURRICULUM_ITEMS_PARAMS).json()
        except conn_error as error:
            logger.fatal(f"Connection error on initial curriculum fetch: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except requests.exceptions.Timeout as error:
            logger.fatal(f"Timeout error on initial curriculum fetch: {error}")
            logger.fatal("This usually happens with very large courses. Try using --save-to-file to cache the data.")
            sys.exit(1)
        except Exception as error:
            logger.fatal(f"Unexpected error on initial curriculum fetch: {error}")
            sys.exit(1)
        else:
            _next = data.get("next")
            _count = data.get("count")
            est_page_count = math.ceil(_count / 100)  # 100 is the max results per page
            
            logger.info(f"> Course has {_count} total items across {est_page_count} pages")
            
            if est_page_count > 50:
                logger.warning(f"> This is a very large course ({est_page_count} pages)!")
                logger.warning("> Consider using --save-to-file to cache curriculum data for faster subsequent runs")
            
            while _next:
                logger.info(f"> Downloading course curriculum.. (Page {page + 1}/{est_page_count})")
                page_success = False
                
                for retry_attempt in range(max_page_retries):
                    try:
                        resp = self.session._get(_next)
                        if not resp.ok:
                            if resp.status_code == 504:
                                logger.warning(f"Gateway timeout (504) on page {page + 1}, attempt {retry_attempt + 1}")
                                if retry_attempt < max_page_retries - 1:
                                    wait_time = min(60, (retry_attempt + 1) * 10)
                                    logger.info(f"Waiting {wait_time} seconds before retrying page...")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    logger.error(f"Failed to fetch page {page + 1} after {max_page_retries} attempts")
                                    break
                            else:
                                logger.error(f"HTTP {resp.status_code} on page {page + 1}, attempt {retry_attempt + 1}")
                                if retry_attempt < max_page_retries - 1:
                                    time.sleep((retry_attempt + 1) * 2)
                                    continue
                                else:
                                    break
                        
                        resp = resp.json()
                        page_success = True
                        break
                        
                    except requests.exceptions.Timeout as error:
                        logger.warning(f"Timeout on page {page + 1}, attempt {retry_attempt + 1}: {error}")
                        if retry_attempt < max_page_retries - 1:
                            wait_time = min(45, (retry_attempt + 1) * 8)
                            logger.info(f"Waiting {wait_time} seconds before retrying page...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"Page {page + 1} timed out after {max_page_retries} attempts")
                            
                    except conn_error as error:
                        logger.warning(f"Connection error on page {page + 1}, attempt {retry_attempt + 1}: {error}")
                        if retry_attempt < max_page_retries - 1:
                            time.sleep((retry_attempt + 1) * 3)
                        else:
                            logger.error(f"Page {page + 1} failed after {max_page_retries} connection attempts")
                            
                    except Exception as error:
                        logger.error(f"Unexpected error on page {page + 1}, attempt {retry_attempt + 1}: {error}")
                        if retry_attempt < max_page_retries - 1:
                            time.sleep((retry_attempt + 1) * 2)
                        else:
                            logger.error(f"Page {page + 1} failed after {max_page_retries} attempts")
                
                if not page_success:
                    logger.error(f"Failed to fetch page {page + 1} after all retry attempts")
                    logger.error("This may result in incomplete course data")
                    # Continue with next page instead of failing completely
                    _next = None
                    break
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
                        page = page + 1
                        
                        # Add a small delay between pages to avoid overwhelming the server
                        if page % 10 == 0:  # Every 10 pages, take a longer break
                            logger.info("> Taking a brief break to avoid server overload...")
                            time.sleep(2)
                        else:
                            time.sleep(0.5)  # Small delay between pages
                    else:
                        logger.warning(f"No results found on page {page + 1}")
                        break
                        
            logger.info(f"> Successfully retrieved curriculum data ({len(data.get('results', []))} items)")
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
                    
                    # Enhanced source extraction with better error handling
                    if sources and isinstance(sources, list):
                        sources = self._extract_sources(sources, skip_hls)
                        logger.debug(f"Extracted {len(sources)} non-encrypted sources for lecture {index}")
                    else:
                        logger.warning(f"No video sources found in stream_urls for lecture {index}")
                        sources = []
                    
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
                    logger.warning(f"stream_urls is not a dict or is empty for lecture {index}")
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        "html_content": asset.get("body"),
                        "extension": "html",
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "sources": [],
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
                    logger.debug(f"Extracted {len(sources)} encrypted sources for lecture {index}")
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
                    logger.warning(f"No media_sources found for encrypted lecture {index}")
                    lecture.pop("data")  # remove the raw data object after processing
                    lecture = {
                        **lecture,
                        "html_content": asset.get("body"),
                        "extension": "html",
                        "assets": retVal,
                        "assets_count": len(retVal),
                        "video_sources": [],
                        "subtitle_count": 0,
                        "sources_count": 0,
                        "is_encrypted": False,
                        "asset_id": asset.get("id"),
                        "type": asset.get("asset_type"),
                    }
        else:
            logger.warning(f"No asset found for lecture {index}")
            lecture = {
                **lecture,
                "assets": retVal,
                "assets_count": len(retVal),
                "sources": [],
                "video_sources": [],
                "asset_id": lecture_data.get("id"),
                "type": lecture_data.get("type"),
                "is_encrypted": False,
                "sources_count": 0,
                "subtitle_count": 0,
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
        
        # Configure session timeouts for large courses
        adapter = requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=5,
                read=5,
                connect=5,
                backoff_factor=1,
                status_forcelist=[502, 503, 504]
            )
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def _set_auth_headers(self, bearer_token=""):
        self._headers["Authorization"] = "Bearer {}".format(bearer_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(bearer_token)

    def _get(self, url, params=None):
        max_retries = 10
        base_timeout = (30, 120)  # (connect_timeout, read_timeout) - increased for large courses
        
        for i in range(max_retries):
            try:
                # Use exponential backoff for timeout - crucial for large courses
                timeout = (base_timeout[0] + (i * 5), base_timeout[1] + (i * 30))
                
                logger.debug(f"Attempting request {i+1}/{max_retries} to {url} with timeout {timeout}")
                
                session = self._session.get(
                    url, 
                    headers=self._headers, 
                    cookies=cj, 
                    params=params,
                    timeout=timeout
                )
                
                if session.ok:
                    logger.debug(f"Request successful on attempt {i+1}")
                    return session
                elif session.status_code in [502, 503, 504]:
                    # Gateway errors - these are common with large courses
                    logger.warning(f"Gateway error {session.status_code} on attempt {i+1}, will retry")
                    if i < max_retries - 1:  # Don't sleep on last attempt
                        # Exponential backoff with jitter for gateway timeouts
                        sleep_time = min(60, (2 ** i) + (i * 0.5))  # Cap at 60 seconds
                        logger.info(f"Waiting {sleep_time:.1f} seconds before retry...")
                        time.sleep(sleep_time)
                    continue
                else:
                    logger.error(f"HTTP {session.status_code} {session.reason} on attempt {i+1}")
                    if i < max_retries - 1:
                        time.sleep(min(10, i + 1))  # Progressive delay
                    
            except requests.exceptions.Timeout as e:
                logger.warning(f"Request timeout on attempt {i+1}/{max_retries}: {e}")
                if i < max_retries - 1:
                    sleep_time = min(30, (i + 1) * 3)  # Progressive timeout handling
                    logger.info(f"Waiting {sleep_time} seconds before retry due to timeout...")
                    time.sleep(sleep_time)
                else:
                    logger.error("Max retries exceeded due to timeouts")
                    raise
                    
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error on attempt {i+1}/{max_retries}: {e}")
                if i < max_retries - 1:
                    sleep_time = min(20, (i + 1) * 2)
                    logger.info(f"Waiting {sleep_time} seconds before retry due to connection error...")
                    time.sleep(sleep_time)
                else:
                    logger.error("Max retries exceeded due to connection errors")
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {i+1}/{max_retries}: {e}")
                if i < max_retries - 1:
                    time.sleep(min(15, i + 2))
                else:
                    raise
        
        logger.error(f"Failed to get response after {max_retries} attempts")
        return session  # Return last response even if failed

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

    if os.name == "nt":
        if use_h265:
            command = f'ffmpeg {transcode} -y -i "{video_filepath}" -i "{audio_filepath}" -c:v {codec} -vtag hvc1 -crf {h265_crf} -preset {h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
        else:
            command = f'ffmpeg -y -i "{video_filepath}" -i "{audio_filepath}" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
    else:
        if use_h265:
            command = f'nice -n 7 ffmpeg {transcode} -y -i "{video_filepath}" -i "{audio_filepath}" -c:v {codec} -vtag hvc1 -crf {h265_crf} -preset {h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
        else:
            command = f'nice -n 7 ffmpeg -y -i "{video_filepath}" -i "{audio_filepath}" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'

    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("FFMPEG-STDOUT", process.stdout)
    log_subprocess_output("FFMPEG-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Muxing returned a non-zero exit code")

    return ret_code


def handle_segments(url, format_id, lecture_id, chapter_dir):
    os.chdir(os.path.join(chapter_dir))

    video_filepath_enc = lecture_id + ".encrypted.mp4"
    audio_filepath_enc = lecture_id + ".encrypted.m4a"

    logger.info("> Downloading Lecture Tracks...")
    args = [
        "yt-dlp",
        "--enable-file-urls",
        "--force-generic-extractor",
        "--allow-unplayable-formats",
        "--concurrent-fragments",
        f"{concurrent_downloads}",
        "--downloader",
        "aria2c",
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
    log_subprocess_output("YTDLP-STDOUT", process.stdout)
    log_subprocess_output("YTDLP-STDERR", process.stderr)
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
        subprocess.Popen(["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for Aria2c, please tell the program author about this! "
        )
        return True


def check_for_ffmpeg():
    try:
        subprocess.Popen(["ffmpeg"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
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
    logger.debug(f"Starting aria2c download: {url} -> {filename}")
    
    args = [
        "aria2c",
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
        "--max-tries=3",
        "--retry-wait=2",
    ]
    
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        
        # Log the output for debugging
        if stdout:
            for line in stdout.splitlines():
                logger.debug(f"[aria2c] {line}")
        if stderr:
            for line in stderr.splitlines():
                logger.debug(f"[aria2c] {line}")
        
        ret_code = process.returncode
        logger.debug(f"aria2c returned code: {ret_code}")
        
    except Exception as e:
        logger.error(f"Error running aria2c: {e}")
        ret_code = 1
    
    # Handle .part files that might not have been renamed properly
    handle_part_files(file_dir, filename)
    
    # Check if the download was successful
    expected_file_path = os.path.join(file_dir, filename)
    if not os.path.exists(expected_file_path):
        logger.warning(f"Download failed - file not found: {filename}")
        # Clean up any empty .part files
        cleanup_empty_part_files(file_dir)
        if ret_code == 0:
            # If aria2c returned success but file is missing, set error code
            ret_code = 1
    elif os.path.getsize(expected_file_path) == 0:
        logger.warning(f"Download failed - file is empty: {filename}")
        # Clean up any empty .part files
        cleanup_empty_part_files(file_dir)
        if ret_code == 0:
            # If aria2c returned success but file is empty, set error code
            ret_code = 1
    else:
        logger.info(f"Download successful: {filename} ({os.path.getsize(expected_file_path)} bytes)")
    
    if ret_code != 0:
        # Try fallback with yt-dlp directly
        logger.info(f"aria2c failed, trying yt-dlp fallback for {filename}")
        try:
            fallback_args = [
                "yt-dlp",
                "--no-playlist",
                "--extractor-args", "youtube:player_client=web",
                "-o", os.path.join(file_dir, filename),
                url
            ]
            
            fallback_process = subprocess.Popen(fallback_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            fallback_stdout, fallback_stderr = fallback_process.communicate()
            
            fallback_ret_code = fallback_process.returncode
            
            if fallback_stdout:
                for line in fallback_stdout.splitlines():
                    logger.debug(f"[yt-dlp] {line}")
            if fallback_stderr:
                for line in fallback_stderr.splitlines():
                    logger.debug(f"[yt-dlp] {line}")
            
            if fallback_ret_code == 0 and os.path.exists(expected_file_path) and os.path.getsize(expected_file_path) > 0:
                logger.info(f"yt-dlp fallback successful: {filename}")
                return 0
            else:
                logger.error(f"yt-dlp fallback also failed for {filename}")
                raise Exception(f"Both aria2c and yt-dlp failed for {filename}")
                
        except Exception as e:
            logger.error(f"yt-dlp fallback error: {e}")
            raise Exception(f"Download failed with return code {ret_code} and fallback failed")
    
    return ret_code


def cleanup_empty_part_files(file_dir):
    """
    Clean up empty .part files and .part.frag.urls files that are created when downloads fail.
    """
    try:
        for file in os.listdir(file_dir):
            if file.endswith('.part'):
                part_file_path = os.path.join(file_dir, file)
                if os.path.getsize(part_file_path) == 0:
                    logger.info(f"Removing empty .part file: {file}")
                    os.remove(part_file_path)
            elif file.endswith('.part.frag.urls'):
                frag_urls_path = os.path.join(file_dir, file)
                logger.info(f"Removing .part.frag.urls file: {file}")
                try:
                    os.remove(frag_urls_path)
                except Exception as e:
                    logger.warning(f"Could not remove {file}: {e}")
    except Exception as e:
        logger.warning(f"Error cleaning up empty .part files in {file_dir}: {e}")


def handle_part_files(file_dir, expected_filename):
    """
    Handle .part files that might not have been renamed properly by aria2c.
    This function renames .part files to their proper names and cleans up .part.frag.urls files.
    """
    try:
        # Look for .part files in the directory
        for file in os.listdir(file_dir):
            if file.endswith('.part'):
                part_file_path = os.path.join(file_dir, file)
                
                # Skip empty .part files - they indicate a failed download
                if os.path.getsize(part_file_path) == 0:
                    logger.info(f"Skipping empty .part file: {file}")
                    continue
                
                # Get the base name without .part extension
                base_name = file[:-5]  # Remove '.part' from the end
                target_file_path = os.path.join(file_dir, base_name)
                
                # Check if the target file doesn't exist or is smaller than the part file
                should_rename = False
                if not os.path.exists(target_file_path):
                    should_rename = True
                elif os.path.getsize(part_file_path) > os.path.getsize(target_file_path):
                    should_rename = True
                
                if should_rename:
                    logger.info(f"Renaming .part file: {file} -> {base_name}")
                    if os.path.exists(target_file_path):
                        os.remove(target_file_path)
                    os.rename(part_file_path, target_file_path)
                    
        # Clean up .part.frag.urls files
        for file in os.listdir(file_dir):
            if file.endswith('.part.frag.urls'):
                frag_urls_path = os.path.join(file_dir, file)
                logger.info(f"Removing .part.frag.urls file: {file}")
                try:
                    os.remove(frag_urls_path)
                except Exception as e:
                    logger.warning(f"Could not remove {file}: {e}")
                    
    except Exception as e:
        logger.warning(f"Error handling .part files in {file_dir}: {e}")


def cleanup_part_files_in_directory(directory):
    """
    Recursively clean up .part and .part.frag.urls files in a directory and all subdirectories.
    """
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.part'):
                    part_file_path = os.path.join(root, file)
                    
                    # Remove empty .part files - they indicate failed downloads
                    if os.path.getsize(part_file_path) == 0:
                        logger.info(f"Removing empty .part file: {file}")
                        try:
                            os.remove(part_file_path)
                        except Exception as e:
                            logger.warning(f"Could not remove empty .part file {file}: {e}")
                        continue
                    
                    # Try to rename non-empty .part files to their proper names
                    base_name = file[:-5]  # Remove '.part' from the end
                    target_file_path = os.path.join(root, base_name)
                    
                    should_rename = False
                    if not os.path.exists(target_file_path):
                        should_rename = True
                    elif os.path.getsize(part_file_path) > os.path.getsize(target_file_path):
                        should_rename = True
                    
                    if should_rename:
                        logger.info(f"Renaming .part file: {file} -> {base_name}")
                        if os.path.exists(target_file_path):
                            os.remove(target_file_path)
                        os.rename(part_file_path, target_file_path)
                        
                elif file.endswith('.part.frag.urls'):
                    # Remove .part.frag.urls files
                    frag_urls_path = os.path.join(root, file)
                    logger.info(f"Removing .part.frag.urls file: {file}")
                    try:
                        os.remove(frag_urls_path)
                    except Exception as e:
                        logger.warning(f"Could not remove {file}: {e}")
                        
    except Exception as e:
        logger.warning(f"Error cleaning up .part files in {directory}: {e}")


def cleanup_empty_subtitle_files(directory):
    """
    Clean up empty subtitle files (.srt, .vtt) that were created during failed downloads.
    """
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(('.srt', '.vtt')):
                    file_path = os.path.join(root, file)
                    if os.path.getsize(file_path) == 0:
                        logger.info(f"Removing empty subtitle file: {file}")
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.warning(f"Could not remove empty subtitle file {file}: {e}")
    except Exception as e:
        logger.warning(f"Error cleaning up empty subtitle files in {directory}: {e}")


def log_lecture_debug_info(lecture, lecture_title):
    """Log detailed information about a lecture for debugging purposes"""
    try:
        logger.debug(f"=== DEBUG INFO for lecture '{lecture_title}' ===")
        logger.debug(f"Lecture ID: {lecture.get('id')}")
        logger.debug(f"Asset ID: {lecture.get('asset_id')}")
        logger.debug(f"Type: {lecture.get('type')}")
        logger.debug(f"Is encrypted: {lecture.get('is_encrypted')}")
        
        # Log sources information
        sources = lecture.get('sources', [])
        video_sources = lecture.get('video_sources', [])
        logger.debug(f"Regular sources count: {len(sources)}")
        logger.debug(f"Video sources count: {len(video_sources)}")
        
        if sources:
            logger.debug("Regular sources:")
            for i, source in enumerate(sources):
                logger.debug(f"  Source {i+1}: {source.get('type')} - {source.get('height')}p - URL: {source.get('download_url', 'NO_URL')[:50]}...")
        
        if video_sources:
            logger.debug("Video sources:")
            for i, source in enumerate(video_sources):
                logger.debug(f"  Video source {i+1}: {source.get('type')} - {source.get('height')}p - URL: {source.get('download_url', 'NO_URL')[:50]}...")
        
        # Log raw data if available
        if lecture.get('data'):
            asset = lecture.get('data', {}).get('asset', {})
            if asset:
                logger.debug(f"Asset type: {asset.get('asset_type')}")
                logger.debug(f"Has stream_urls: {asset.get('stream_urls') is not None}")
                logger.debug(f"Has media_sources: {asset.get('media_sources') is not None}")
                
                stream_urls = asset.get('stream_urls')
                if stream_urls and isinstance(stream_urls, dict):
                    video_streams = stream_urls.get('Video', [])
                    logger.debug(f"Video streams in stream_urls: {len(video_streams)}")
                
                media_sources = asset.get('media_sources', [])
                logger.debug(f"Media sources count: {len(media_sources)}")
        
        logger.debug(f"=== END DEBUG INFO for lecture '{lecture_title}' ===")
        
    except Exception as e:
        logger.error(f"Error logging debug info for lecture '{lecture_title}': {e}")


def should_download_caption(caption_language: str, caption_locale: str) -> bool:
    """
    Determine if a caption should be downloaded based on user preference
    
    Args:
        caption_language: The language of the caption (e.g., 'en', 'ar')
        caption_locale: User preference (e.g., 'en', 'ar', 'en,ar', 'all')
    
    Returns:
        bool: True if caption should be downloaded
    """
    if not caption_locale or caption_locale.lower() == "none":
        return False
    
    if caption_locale.lower() == "all":
        return True
    
    # Handle multiple languages (e.g., "en,ar")
    if "," in caption_locale:
        requested_languages = [lang.strip().lower() for lang in caption_locale.split(",")]
        return caption_language.lower() in requested_languages
    
    # Single language
    return caption_language.lower() == caption_locale.lower()


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
            
            # Verify the caption file was downloaded successfully
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                logger.warning(f"    > Caption download failed - file not found or empty: {filename}")
                if tries < 2:  # Allow 3 total attempts
                    logger.info(f"    > Retrying caption download (attempt {tries + 1}/3)")
                    time.sleep(1)
                    process_caption(caption, lecture_id, lecture_title, lecture_dir, tries + 1)
                    return
                else:
                    logger.error(f"    > Caption download failed after 3 attempts: {filename}")
                    return
                    
        except Exception as e:
            error_message = str(e)
            if "status=403" in error_message or "Forbidden" in error_message:
                logger.error(f"    > Error downloading caption: {e}. Access denied (403 Forbidden), skipping further retries.")
                return
            elif tries >= 2:  # Allow 3 total attempts
                logger.error(f"    > Error downloading caption: {e}. Exceeded retries, skipping.")
                return
            else:
                logger.error(f"    > Error downloading caption: {e}. Will retry {2-tries} more times.")
                time.sleep(1)
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
    
    # Enhanced logging for debugging
    logger.debug(f"Processing lecture: {lecture_title}")
    logger.debug(f"Is encrypted: {is_encrypted}")
    logger.debug(f"Has video_sources: {lecture_sources is not None and len(lecture_sources) > 0 if lecture_sources else False}")
    logger.debug(f"Has sources: {lecture.get('sources') is not None and len(lecture.get('sources', [])) > 0 if lecture.get('sources') else False}")
    
    # Log detailed lecture information for troubleshooting
    log_lecture_debug_info(lecture, lecture_title)

    if is_encrypted:
        if lecture_sources and len(lecture_sources) > 0:
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
            logger.warning(f"      > Lecture '{lecture_title}' is missing DRM media links")
            logger.debug(f"Lecture video_sources count: {len(lecture_sources) if lecture_sources else 0}")
            # Try to download as non-encrypted if no DRM sources available
            logger.info(f"      > Attempting to download '{lecture_title}' as non-encrypted fallback")
            try_download_as_non_encrypted(lecture, lecture_path, chapter_dir)
    else:
        sources = lecture.get("sources")
        if not sources:
            logger.warning(f"      > Lecture '{lecture_title}' has no sources, attempting alternative download methods")
            try_download_as_non_encrypted(lecture, lecture_path, chapter_dir)
            return
            
        sources = sorted(sources, key=lambda x: int(x.get("height", 0)), reverse=True)
        if not os.path.isfile(lecture_path):
            logger.info("      > Lecture doesn't have DRM, attempting to download...")
            download_success = False
            max_retries = 3
            
            # Try each available source quality
            for source_idx, source in enumerate(sources):
                if download_success:
                    break
                    
                logger.info(f"      ====== Trying source {source_idx + 1}/{len(sources)}: {source.get('type')} {source.get('height')}")
                
                for attempt in range(max_retries):
                    try:
                        url = source.get("download_url")
                        source_type = source.get("type")
                        
                        if not url:
                            logger.warning(f"      > Source {source_idx + 1} has no download URL")
                            break
                        
                        logger.debug(f"      > Download URL: {url}")
                        
                        if source_type == "hls":
                            download_success = try_hls_download(url, lecture_path, lecture_title)
                        else:
                            download_success = try_direct_download(url, chapter_dir, lecture_title, source_type)
                        
                        if download_success:
                            break
                        else:
                            logger.warning(f"      > {source_type.upper()} Download failed (attempt {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                time.sleep(2)  # Wait before retry
                                    
                    except Exception as e:
                        logger.warning(f"      > Download attempt {attempt + 1} failed with exception: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(2)  # Wait before retry
                
                if not download_success:
                    logger.warning(f"      > Failed to download with source {source_idx + 1}, trying next source...")
                    time.sleep(1)  # Brief pause before trying next source
            
            if not download_success:
                logger.error(f"      > Failed to download lecture '{lecture_title}' with all available sources")
                # Try alternative download methods
                try_alternative_download_methods(lecture, lecture_path, chapter_dir)
                # Clean up any partial files
                cleanup_empty_part_files(chapter_dir)
        else:
            logger.info(f"      > Lecture '{lecture_title}' is already downloaded, skipping...")


def try_hls_download(url, lecture_path, lecture_title):
    """Try downloading HLS stream"""
    try:
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
        
        if ret_code == 0 and os.path.exists(lecture_path) and os.path.getsize(lecture_path) > 0:
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
            return True
        return False
    except Exception as e:
        logger.error(f"      > HLS download error: {e}")
        return False


def try_direct_download(url, chapter_dir, lecture_title, source_type):
    """Try direct download using aria2c"""
    try:
        filename = f"{lecture_title}.mp4"
        ret_code = download_aria(url, chapter_dir, filename)
        expected_file = os.path.join(chapter_dir, filename)
        
        if os.path.exists(expected_file) and os.path.getsize(expected_file) > 0:
            logger.debug(f"      > {source_type} Download return code: {ret_code}")
            return True
        else:
            logger.warning(f"      > {source_type} Download failed - file not found or empty")
            return False
    except Exception as e:
        logger.error(f"      > {source_type} download error: {e}")
        return False


def try_download_as_non_encrypted(lecture, lecture_path, chapter_dir):
    """Fallback method to try downloading as non-encrypted when no sources are available"""
    try:
        lecture_id = lecture.get("id")
        lecture_title = lecture.get("lecture_title")
        
        logger.info(f"      > Attempting fallback download for '{lecture_title}'")
        
        # Try to re-parse the lecture data to see if we can extract sources
        lecture_data = lecture.get("data")
        if lecture_data:
            logger.info(f"      > Re-parsing lecture data to find sources...")
            
            # Try to extract sources from the raw data
            asset = lecture_data.get("asset")
            if asset:
                # Check for alternative source locations
                alternative_sources = []
                
                # Check stream_urls
                stream_urls = asset.get("stream_urls")
                if stream_urls and isinstance(stream_urls, dict):
                    video_sources = stream_urls.get("Video")
                    if video_sources:
                        alternative_sources.extend(video_sources)
                
                # Check media_sources (sometimes non-encrypted videos are here too)
                media_sources = asset.get("media_sources")
                if media_sources and isinstance(media_sources, list):
                    alternative_sources.extend(media_sources)
                
                # Check for direct download URLs in other fields
                download_url = asset.get("download_url")
                if download_url:
                    alternative_sources.append({"download_url": download_url, "type": "video"})
                
                if alternative_sources:
                    logger.info(f"      > Found {len(alternative_sources)} alternative sources")
                    # Try to download using these alternative sources
                    for idx, source in enumerate(alternative_sources):
                        url = source.get("download_url")
                        if url:
                            logger.info(f"      > Trying alternative source {idx + 1}: {url}")
                            success = try_direct_download(url, chapter_dir, lecture_title, "alternative")
                            if success:
                                logger.info(f"      > Successfully downloaded using alternative source {idx + 1}")
                                return
                            else:
                                logger.warning(f"      > Alternative source {idx + 1} failed")
                else:
                    logger.warning(f"      > No alternative sources found in asset data")
        
        # If all else fails, try to construct a Udemy lecture URL
        logger.info(f"      > Attempting to construct Udemy lecture URL...")
        success = try_udemy_lecture_url_download(lecture, lecture_path, chapter_dir)
        if not success:
            logger.warning(f"      > No direct download method available for '{lecture_title}' - manual intervention may be required")
        
    except Exception as e:
        logger.error(f"      > Fallback download error: {e}")


def try_udemy_lecture_url_download(lecture, lecture_path, chapter_dir):
    """Try to download using a constructed Udemy lecture URL"""
    try:
        lecture_id = lecture.get("id")
        lecture_title = lecture.get("lecture_title")
        
        # This would require the course URL and portal name
        # For now, we'll just log the approach
        logger.info(f"      > Would attempt to construct URL: https://[portal].udemy.com/course/[course]/learn/lecture/{lecture_id}")
        logger.info(f"      > This requires course URL and portal information")
        
        # In a full implementation, you would:
        # 1. Get the course URL from global variables
        # 2. Get the portal name
        # 3. Construct the lecture URL
        # 4. Use yt-dlp to download from that URL
        
        return False
        
    except Exception as e:
        logger.error(f"      > Udemy URL download error: {e}")
        return False


def try_alternative_download_methods(lecture, lecture_path, chapter_dir):
    """Try alternative download methods when standard methods fail"""
    try:
        lecture_id = lecture.get("id")
        lecture_title = lecture.get("lecture_title")
        
        logger.info(f"      > Trying alternative download methods for '{lecture_title}'")
        
        # Method 1: Try yt-dlp with different extractors and no aria2c
        logger.info(f"      > Trying yt-dlp without aria2c downloader...")
        success = try_ytdlp_direct_download(lecture_path, lecture_title)
        if success:
            return
        
        # Method 2: Try with different yt-dlp options
        logger.info(f"      > Trying yt-dlp with different options...")
        success = try_ytdlp_with_options(lecture_path, lecture_title)
        if success:
            return
        
        # Method 3: Try with curl/wget as fallback (if available)
        logger.info(f"      > Trying curl fallback...")
        success = try_curl_fallback(lecture, lecture_path, chapter_dir)
        if success:
            return
        
        logger.warning(f"      > All alternative methods failed for '{lecture_title}'")
        
    except Exception as e:
        logger.error(f"      > Alternative download methods error: {e}")


def try_ytdlp_direct_download(lecture_path, lecture_title):
    """Try yt-dlp without aria2c downloader"""
    try:
        temp_filepath = lecture_path.replace(".mp4", ".%(ext)s")
        cmd = [
            "yt-dlp",
            "--enable-file-urls",
            "--force-generic-extractor",
            "--no-downloader-args",
            "--concurrent-fragments",
            "1",  # Reduce concurrent fragments
            "-o",
            f"{temp_filepath}",
            "--extractor-args", "youtube:player_client=web",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--referer", "https://www.udemy.com/",
        ]
        
        # We need a URL to download from - this would need to be provided
        # For now, we'll just log that this method is available
        logger.info(f"      > yt-dlp direct method ready (URL required)")
        return False
        
    except Exception as e:
        logger.error(f"      > yt-dlp direct download error: {e}")
        return False


def try_ytdlp_with_options(lecture_path, lecture_title):
    """Try yt-dlp with different options"""
    try:
        temp_filepath = lecture_path.replace(".mp4", ".%(ext)s")
        cmd = [
            "yt-dlp",
            "--enable-file-urls",
            "--force-generic-extractor",
            "--no-downloader-args",
            "--concurrent-fragments",
            "1",
            "--fragment-retries", "3",
            "--retries", "3",
            "--socket-timeout", "30",
            "--no-check-certificate",
            "-o",
            f"{temp_filepath}",
        ]
        
        logger.info(f"      > yt-dlp with options ready (URL required)")
        return False
        
    except Exception as e:
        logger.error(f"      > yt-dlp with options error: {e}")
        return False


def try_curl_fallback(lecture, lecture_path, chapter_dir):
    """Try curl as a fallback download method"""
    try:
        # This would require the actual download URL
        # For now, we'll just check if curl is available
        import shutil
        if shutil.which("curl"):
            logger.info(f"      > curl is available for fallback downloads")
            return False
        else:
            logger.info(f"      > curl not available")
            return False
            
    except Exception as e:
        logger.error(f"      > curl fallback error: {e}")
        return False


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


def parse_new(udemy: Udemy, udemy_object: dict, no_report: bool = False):
    # Prepare chapters/videos structure for selection GUI
    chapters_for_gui = []
    for chapter in udemy_object.get("chapters", []):
        chapter_dict = {
            "id": chapter.get("chapter_index"),
            "title": chapter.get("chapter_title"),
            "videos": []
        }
        for lecture in chapter.get("lectures", []):
            # Add both video lectures and quizzes
            if lecture.get("_class") in ["lecture", "quiz"]:
                # Try to get thumbnail if available (add logic if you have thumbnail URLs)
                thumb_url = lecture.get("data", {}).get("asset", {}).get("thumbnail_url")
                lecture_type = "quiz" if lecture.get("_class") == "quiz" else "video"
                
                # Check if lecture has supplementary assets
                has_assets = False
                supp_assets = lecture.get("data", {}).get("supplementary_assets", [])
                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                    has_assets = True
                
                # Check if this is a file-type lecture (not a video)
                asset_type = None
                asset_filename = None
                asset = lecture.get("data", {}).get("asset", {})
                if isinstance(asset, dict):
                    asset_type = asset.get("asset_type", "").lower()
                    asset_filename = asset.get("filename")
                    if asset_type in ["article", "file", "e-book", "ebook", "presentation", "audio"]:
                        lecture_type = "file"
                
                chapter_dict["videos"].append({
                    "id": lecture.get("id"),
                    "title": lecture.get("lecture_title"),
                    "thumbnail_url": thumb_url,
                    "type": lecture_type,
                    "has_assets": has_assets,
                    "asset_type": asset_type,
                    "asset_filename": asset_filename
                })
        chapters_for_gui.append(chapter_dict)

    if id_as_course_name:
        course_name = str(udemy_object.get("course_id"))
    else:
        course_name = (
            udemy_object.get("course_title")
            or udemy_object.get("title")
            or udemy_object.get("course_id")
            or "udemy-course"
        )
    course_dir = os.path.join(DOWNLOAD_DIR, sanitize_filename(str(course_name)))
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
        if chapter_index is None:
            chapter_index = current_chapter_index
            
        if not chapter_title:
            chapter_title = f"Chapter {chapter_index}"
            
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
                    # Enhanced debugging for problematic lectures
                    logger.debug(f"      > Lecture details: ID={parsed_lecture.get('id')}, Type={parsed_lecture.get('type')}")
                    logger.debug(f"      > Is encrypted: {parsed_lecture.get('is_encrypted')}")
                    logger.debug(f"      > Sources count: {parsed_lecture.get('sources_count', 0)}")
                    logger.debug(f"      > Video sources count: {len(parsed_lecture.get('video_sources', []))}")
                    logger.debug(f"      > Regular sources: {len(parsed_lecture.get('sources', []))}")
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
                
                # Track which languages we're downloading
                downloading_languages = []
                
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if should_download_caption(lang, caption_locale):
                        downloading_languages.append(lang)
                        process_caption(subtitle, parsed_lecture.get("id"), lecture_title, chapter_dir)
                
                if downloading_languages:
                    logger.info(f"    > Downloaded captions for languages: {', '.join(downloading_languages)}")
                else:
                    logger.info(f"    > No captions matched language preference: {caption_locale}")

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
        
        # ===== CHAPTER COMPLETION PROCESSING =====
        # After processing all lectures in this chapter, verify downloads, decrypt if needed, and combine files
        logger.info(f"\n--- Chapter {chapter_index} download complete, processing files ---")
        
        # Get decryption key from environment variable or leave empty if not available
        # Note: In CLI mode, this could be passed as a parameter instead
        decryption_key_for_chapter = os.getenv("UDEMY_DECRYPTION_KEY", "")
        
        # Get ffmpeg path
        ffmpeg_path = "ffmpeg"  # Use system ffmpeg by default
        if os.path.exists("./ffmpeg.exe"):
            ffmpeg_path = "./ffmpeg.exe"
        
        try:
            # Process this chapter's completion (verify, decrypt, combine)
            chapter_results = process_chapter_completion(
                chapter_dir=chapter_dir,
                chapter_index=chapter_index,
                chapter_lectures=chapter.get("lectures", []),
                decryption_key=decryption_key_for_chapter,
                id_to_title_map=id_to_title_map,
                ffmpeg_path=ffmpeg_path
            )
            
            # Log chapter processing results
            verification = chapter_results.get('verification', {})
            logger.info(f"Chapter {chapter_index} processing summary:")
            logger.info(f"  - Complete: {len(verification.get('complete', []))}")
            logger.info(f"  - Encrypted pending: {len(verification.get('encrypted_pending', []))}")
            logger.info(f"  - Incomplete: {len(verification.get('incomplete', []))}")
            logger.info(f"  - Missing: {len(verification.get('missing', []))}")

            
        except Exception as e:
            logger.error(f"Error during chapter {chapter_index} completion processing: {e}")
            logger.exception("Full traceback:")
        # ===== END CHAPTER COMPLETION PROCESSING =====
    
    # ===== FINAL COURSE VERIFICATION AND REPORT =====
    # Only run if not disabled
    if not no_report:
        # After all chapters are processed, generate final course-wide verification report
        logger.info("\n" + "="*60)
        logger.info("ALL CHAPTERS COMPLETE - Generating Final Verification Report")
        logger.info("="*60)
        
        try:
            from download_verifier import verify_course_downloads, generate_verification_report
            import webbrowser
            
            # Run full course verification
            logger.info("Running final course-wide verification...")
            final_results = verify_course_downloads(course_dir, id_to_title_map)
            
            # Generate HTML and JSON reports
            course_name = os.path.basename(course_dir)
            html_report_path = generate_verification_report(course_dir, course_name, final_results)
            
            # Log summary
            total = len(final_results['complete']) + len(final_results['incomplete']) + \
                    len(final_results['missing']) + len(final_results['encrypted_pending'])
            logger.info(f"\nFinal Verification Summary:")
            logger.info(f"  Total Lectures: {total}")
            logger.info(f"  ✓ Complete: {len(final_results['complete'])}")
            logger.info(f"  🔒 Encrypted Pending: {len(final_results['encrypted_pending'])}")
            logger.info(f"  ⚠ Incomplete: {len(final_results['incomplete'])}")
            logger.info(f"  ✗ Missing: {len(final_results['missing'])}")
            
            success_rate = (len(final_results['complete']) / total * 100) if total > 0 else 0
            logger.info(f"  Success Rate: {success_rate:.1f}%")
            
            # Auto-open HTML report in browser
            if html_report_path and os.path.exists(html_report_path):
                logger.info(f"\n✓ Verification report saved: {html_report_path}")
                logger.info("Opening report in browser...")
                try:
                    webbrowser.open('file://' + os.path.abspath(html_report_path))
                    logger.info("✓ Report opened in browser")
                except Exception as e:
                    logger.warning(f"Could not open browser: {e}")
                    logger.info(f"Please manually open: {html_report_path}")
            
        except Exception as e:
            logger.error(f"Error generating final verification report: {e}")
            logger.exception("Full traceback:")
    else:
        logger.info("Skipping final verification report (--no-report specified)")
    
    logger.info("\n" + "="*60)
    logger.info("DOWNLOAD AND PROCESSING COMPLETE!")
    logger.info("="*60 + "\n")
    # ===== END FINAL COURSE VERIFICATION =====


def decrypt_chapter_files(decryption_key: str, chapter_dir: str, ffmpeg_path: str = "ffmpeg") -> bool:
    """
    Decrypt all encrypted files in a single chapter directory
    
    Args:
        decryption_key: The DRM decryption key
        chapter_dir: Path to the chapter directory
        ffmpeg_path: Path to ffmpeg executable (default: "ffmpeg")
        
    Returns:
        True if decryption succeeded, False otherwise
    """
    import subprocess
    
    if not decryption_key:
        logger.warning(f"No decryption key provided for chapter: {chapter_dir}")
        return False
    
    if not os.path.exists(chapter_dir):
        logger.error(f"Chapter directory does not exist: {chapter_dir}")
        return False
    
    encrypted_files_found = False
    all_successful = True
    
    logger.info(f"Starting decryption in chapter: {os.path.basename(chapter_dir)}")
    
    for file in os.listdir(chapter_dir):
        if file.endswith(".encrypted.mp4") or file.endswith(".encrypted.m4a"):
            encrypted_files_found = True
            in_path = os.path.join(chapter_dir, file)
            base_name = file.replace(".encrypted", "")
            out_path = os.path.join(chapter_dir, base_name)
            
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                logger.info(f"  > Skipping already decrypted: {base_name}")
                continue
            
            logger.info(f"  > Decrypting: {file}")
            cmd = [ffmpeg_path, "-nostdin", "-loglevel", "error", "-decryption_key", 
                   decryption_key, "-i", in_path, "-c", "copy", out_path]
            
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                
                if proc.returncode != 0:
                    logger.error(f"  > Error decrypting {file}: ffmpeg exited with code {proc.returncode}")
                    if stderr:
                        logger.error(f"  > FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")
                    all_successful = False
                elif not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                    logger.error(f"  > Decryption failed: Output file not created or empty for {file}")
                    all_successful = False
                else:
                    logger.info(f"  > Successfully decrypted: {base_name}")
            except Exception as e:
                logger.error(f"  > Error running ffmpeg for {file}: {e}")
                all_successful = False
    
    if not encrypted_files_found:
        logger.info(f"  > No encrypted files found in chapter")
        return True
    
    return all_successful


def combine_chapter_files(chapter_dir: str, id_to_title_map: Dict[str, str], 
                         ffmpeg_path: str = "ffmpeg") -> bool:
    """
    Combine video/audio files and rename them using the title map for a single chapter
    
    Args:
        chapter_dir: Path to the chapter directory
        id_to_title_map: Mapping of lecture IDs to titles
        ffmpeg_path: Path to ffmpeg executable (default: "ffmpeg")
        
    Returns:
        True if combining succeeded, False otherwise
    """
    import subprocess
    import re
    
    if not os.path.exists(chapter_dir):
        logger.error(f"Chapter directory does not exist: {chapter_dir}")
        return False
    
    logger.info(f"Combining files in chapter: {os.path.basename(chapter_dir)}")
    all_successful = True
    
    for file in os.listdir(chapter_dir):
        # Only process .mp4 files that aren't encrypted
        if file.endswith(".mp4") and ".encrypted" not in file:
            file_id = file[:-4]
            mp4_path = os.path.join(chapter_dir, file)
            m4a_path = os.path.join(chapter_dir, f"{file_id}.m4a")
            
            # Determine final name
            lecture_title = id_to_title_map.get(file_id)
            if lecture_title:
                final_base_name = sanitize_filename(lecture_title)
                final_base_name = deEmojify(final_base_name)
            else:
                final_base_name = file_id
            
            final_output_name = f"{final_base_name}.mp4"
            final_output_path = os.path.join(chapter_dir, final_output_name)
            
            if os.path.exists(mp4_path) and os.path.exists(m4a_path):
                # Both video and audio exist - need to combine
                if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                    logger.info(f"  > Skipping already combined: {final_output_name}")
                    continue
                
                logger.info(f"  > Combining: {file}")
                cmd = [ffmpeg_path, "-nostdin", "-loglevel", "error", "-i", mp4_path, "-i", m4a_path,
                       "-copyts", "-start_at_zero", "-map", "0:v:0", "-map", "1:a:0",
                       "-c:v", "copy", "-c:a", "copy", "-shortest", final_output_path]
                
                try:
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = proc.communicate()
                    
                    if proc.returncode == 0 and os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                        logger.info(f"  > Successfully combined: {final_output_name}")
                        
                        # Define encrypted paths for cleanup
                        encrypted_mp4 = os.path.join(chapter_dir, f"{file_id}.encrypted.mp4")
                        encrypted_m4a = os.path.join(chapter_dir, f"{file_id}.encrypted.m4a")

                        # Backup instead of delete
                        trash_dir = os.path.join(chapter_dir, "_trash")
                        os.makedirs(trash_dir, exist_ok=True)
                        
                        for temp_file in [mp4_path, m4a_path, encrypted_mp4, encrypted_m4a]:
                            if os.path.exists(temp_file):
                                try:
                                    import shutil
                                    dst = os.path.join(trash_dir, os.path.basename(temp_file))
                                    if os.path.exists(dst):
                                        os.remove(dst)
                                    shutil.move(temp_file, dst)
                                except Exception as e:
                                    logger.warning(f"  > Could not move temp file to trash: {e}")
                        
                        # Clean up potential .tmp files left by yt-dlp or ffmpeg
                        tmp_file = f"{final_output_path}.tmp"
                        if os.path.exists(tmp_file):
                            try:
                                os.remove(tmp_file)
                                logger.info(f"  > Removed temp file: {os.path.basename(tmp_file)}")
                            except Exception as e:
                                logger.warning(f"  > Could not remove temp file {os.path.basename(tmp_file)}: {e}")
                        
                        # Rename associated subtitle files
                        _rename_subtitle_files(chapter_dir, file_id, final_base_name)
                    else:
                        logger.error(f"  > Failed to combine {file}")
                        if stderr:
                            logger.error(f"  > FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")
                        all_successful = False
                except Exception as e:
                    logger.error(f"  > Error combining {file}: {e}")
                    all_successful = False
                    
            elif os.path.exists(mp4_path) and lecture_title:
                # Only MP4 exists - just rename if it's a numeric ID
                if file_id.isdigit() and file_id in id_to_title_map:
                    if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                        # Final file exists, remove the ID file
                        try:
                            if mp4_path != final_output_path:
                                os.remove(mp4_path)
                        except Exception:
                            pass
                        continue
                    
                    logger.info(f"  > Renaming: {file} -> {final_output_name}")
                    try:
                        os.rename(mp4_path, final_output_path)
                        
                        # Clean up potential .tmp files
                        tmp_file = f"{final_output_path}.tmp"
                        if os.path.exists(tmp_file):
                            try:
                                os.remove(tmp_file)
                                logger.info(f"  > Removed temp file: {os.path.basename(tmp_file)}")
                            except Exception:
                                pass
                                
                        _rename_subtitle_files(chapter_dir, file_id, final_base_name)
                    except Exception as e:
                        logger.error(f"  > Error renaming {file}: {e}")
                        all_successful = False
    
    return all_successful


def _rename_subtitle_files(chapter_dir: str, file_id: str, final_base_name: str):
    """Helper function to rename subtitle files associated with a lecture"""
    import re
    
    try:
        for srt_file in os.listdir(chapter_dir):
            if srt_file.startswith(file_id) and srt_file.endswith(".srt"):
                # Extract language suffix if present
                lang_match = re.search(r'(_[a-z]{2,3}(?:_[A-Z]{2,3})?).srt$', srt_file)
                if lang_match:
                    lang_part = lang_match.group(1)
                    old_srt_path = os.path.join(chapter_dir, srt_file)
                    new_srt_name = f"{final_base_name}{lang_part}.srt"
                    new_srt_path = os.path.join(chapter_dir, new_srt_name)
                    
                    if not os.path.exists(new_srt_path):
                        os.rename(old_srt_path, new_srt_path)
                        logger.info(f"  > Renamed caption: {srt_file} -> {new_srt_name}")
    except Exception as e:
        logger.warning(f"Error renaming subtitles for {file_id}: {e}")


def process_chapter_completion(chapter_dir: str, chapter_index: int, chapter_lectures: List[Dict],
                               decryption_key: str, id_to_title_map: Dict[str, str],
                               ffmpeg_path: str = "ffmpeg") -> Dict:
    """
    Process chapter completion: verify downloads, decrypt if needed, and combine files
    
    Args:
        chapter_dir: Path to chapter directory
        chapter_index: Chapter index number
        chapter_lectures: List of lecture dicts for this chapter
        decryption_key: DRM decryption key (can be empty if no encrypted content)
        id_to_title_map: Mapping of lecture IDs to titles
        ffmpeg_path: Path to ffmpeg executable
        
    Returns:
        Dict with processing results
    """
    from download_verifier import verify_chapter_downloads
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Chapter {chapter_index} Completion")
    logger.info(f"{'='*60}")
    
    # Check ffmpeg availability
    import shutil
    if not shutil.which(ffmpeg_path) and not os.path.exists(ffmpeg_path):
        logger.error(f"CRITICAL: FFmpeg not found at '{ffmpeg_path}'. Decryption and combining will fail.")
        logger.error("Please install FFmpeg and add it to your PATH, or place ffmpeg.exe in the application folder.")
        return results

    results = {
        'verification': None,
        'decryption_success': True,
        'combining_success': True
    }
    
    # Step 1: Verify downloads
    logger.info("\n[Step 1/3] Verifying chapter downloads...")
    verification_results = verify_chapter_downloads(chapter_dir, chapter_lectures, id_to_title_map)
    results['verification'] = verification_results
    
    complete_count = len(verification_results['complete'])
    encrypted_count = len(verification_results['encrypted_pending'])
    incomplete_count = len(verification_results['incomplete'])
    missing_count = len(verification_results['missing'])
    
    logger.info(f"  > Complete: {complete_count}")
    logger.info(f"  > Encrypted (pending): {encrypted_count}")
    logger.info(f"  > Incomplete: {incomplete_count}")
    logger.info(f"  > Missing: {missing_count}")
    
    # Step 2: Decrypt if needed
    if encrypted_count > 0:
        logger.info("\n[Step 2/3] Decrypting chapter files...")
        if decryption_key:
            results['decryption_success'] = decrypt_chapter_files(decryption_key, chapter_dir, ffmpeg_path)
            if results['decryption_success']:
                logger.info("  > Chapter decryption completed successfully")
            else:
                logger.warning("  > Some decryption operations failed")
        else:
            logger.warning("  > Encrypted files found but no decryption key provided")
            logger.warning("  > Skipping decryption - files will remain encrypted")
            results['decryption_success'] = False
    else:
        logger.info("\n[Step 2/3] No encrypted files - skipping decryption")
    
    # Step 3: Combine and rename files
    logger.info("\n[Step 3/3] Combining and renaming files...")
    results['combining_success'] = combine_chapter_files(chapter_dir, id_to_title_map, ffmpeg_path)
    if results['combining_success']:
        logger.info("  > Chapter file combining completed successfully")
    else:
        logger.warning("  > Some combining operations failed")
        
    # Step 4: Final Cleanup of any remaining .tmp files
    logger.info("\n[Step 4/4] Final cleanup of temp files...")
    try:
        for filename in os.listdir(chapter_dir):
            if filename.endswith(".tmp"):
                file_path = os.path.join(chapter_dir, filename)
                try:
                    os.remove(file_path)
                    logger.info(f"  > Removed leftover temp file: {filename}")
                except Exception as e:
                    logger.warning(f"  > Could not remove temp file {filename}: {e}")
    except Exception as e:
        logger.warning(f"Error during final cleanup: {e}")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Chapter {chapter_index} Processing Complete")
    logger.info(f"{'='*60}\n")
    
    return results



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


def main(args):
    global bearer_token, portal_name
    aria_ret_val = check_for_aria()
    if not aria_ret_val:
        logger.warning("> Aria2c is missing from your system or path! Some downloads may not work.")
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
    logger.info("> For very large courses (100+ chapters), this process may take several minutes")
    logger.info("> If you encounter timeout errors, consider using --save-to-file to cache the data")
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
            
            # Provide helpful information about large courses
            total_chapters = udemy_object["total_chapters"]
            total_lectures = udemy_object["total_lectures"]
            
            if total_chapters > 100 or total_lectures > 500:
                logger.warning(f"> This is a large course: {total_chapters} chapters, {total_lectures} lectures")
                logger.warning("> For better performance with large courses, consider using:")
                logger.warning(">   --save-to-file (to cache curriculum data)")
                logger.warning(">   --chapter filtering (to download in chunks)")
                if not save_to_file:
                    logger.info("> Tip: Add --save-to-file to cache this course data for faster subsequent runs")

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
            parse_new(udemy, udemy_object, no_report=args.no_report)
            
    # Clean up any remaining .part files and empty subtitle files after the download process
    logger.info("Cleaning up any remaining .part files and empty subtitle files...")
    cleanup_part_files_in_directory(DOWNLOAD_DIR)
    cleanup_empty_subtitle_files(DOWNLOAD_DIR)


if __name__ == "__main__":
    # pre run parses arguments, sets up logging, and creates directories
    args = pre_run()
    # run main program
    main(args)
