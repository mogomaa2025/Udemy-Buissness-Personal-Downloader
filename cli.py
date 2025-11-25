# -*- coding: utf-8 -*-
"""
Interactive CLI version of Udemy Downloader with chapter selection
Similar functionality to the GUI but with command-line interface
"""

import json
import os
import sys
import time
from typing import List, Tuple, Dict, Any


CLI_KEY_ALIASES = {
    "course": "course_url",
    "url": "course_url",
    "courseurl": "course_url",
    "token": "token",
    "bearer": "token",
    "chapter": "chapter",
    "chapters": "chapter",
    "lecture": "lecture",
    "lectures": "lecture",
    "quality": "quality",
    "lang": "lang",
    "language": "lang",
    "languages": "lang",
    "caption": "lang",
    "captions": "lang",
    "output": "out_dir",
    "out": "out_dir",
    "output_dir": "out_dir",
    "outdir": "out_dir",
    "browser": "browser",
    "concurrent": "concurrent",
    "concurrency": "concurrent",
    "download_assets": "download_assets",
    "download_captions": "download_captions",
    "download_quizzes": "download_quizzes",
    "keep_vtt": "keep_vtt",
    "skip_lectures": "skip_lectures",
    "skip_hls": "skip_hls",
    "info": "info",
    "id_as_course_name": "id_as_course_name",
    "subscription_course": "subscription_course",
    "save_to_file": "save_to_file",
    "load_from_file": "load_from_file",
    "continue_lecture_numbers": "continue_lecture_numbers",
    "use_h265": "use_h265",
    "use_nvenc": "use_nvenc",
}

CLI_BOOL_KEYS = {
    "download_assets",
    "download_captions",
    "download_quizzes",
    "keep_vtt",
    "skip_lectures",
    "skip_hls",
    "info",
    "id_as_course_name",
    "subscription_course",
    "save_to_file",
    "load_from_file",
    "continue_lecture_numbers",
    "use_h265",
    "use_nvenc",
}

CLI_INT_KEYS = {
    "quality",
    "concurrent",
}


def _str_to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_cli_overrides() -> Dict[str, Any]:
    """Parse simple command-line overrides (key=value or positional)."""
    overrides: Dict[str, Any] = {}
    positional: List[str] = []

    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            # Ignore legacy argparse style flags for this CLI mode
            continue
        if "=" in arg:
            raw_key, raw_value = arg.split("=", 1)
            key = CLI_KEY_ALIASES.get(raw_key.strip().lower(), raw_key.strip().lower())
            overrides[key] = raw_value.strip()
        elif arg:
            positional.append(arg)

    if positional and "course_url" not in overrides:
        overrides["course_url"] = positional[0]
    if len(positional) > 1 and "token" not in overrides:
        overrides["token"] = positional[1]

    normalized: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key in CLI_BOOL_KEYS:
            normalized[key] = _str_to_bool(value)
        elif key in CLI_INT_KEYS:
            try:
                normalized[key] = int(value)
            except ValueError:
                continue
        else:
            normalized[key] = value

    return normalized


def initialize_main_environment(course_info: Dict[str, Any], options: Dict[str, Any], original_argv: List[str]) -> None:
    """Prepare main.py environment by invoking pre_run with synthesized arguments."""
    arg_list: List[str] = ["cli.py", "--course-url", course_info["course_url"]]

    token = course_info.get("token")
    if token:
        arg_list += ["--bearer", token]

    output_dir = options.get("output_dir") or options.get("out_dir")
    if output_dir:
        arg_list += ["--out", output_dir]

    loglevel = options.get("loglevel")
    if loglevel:
        arg_list += ["--log-level", str(loglevel)]

    quality_value = options.get("quality")
    if quality_value:
        arg_list += ["--quality", str(quality_value)]

    caption_languages = options.get("caption_languages") or options.get("lang")
    if caption_languages:
        arg_list += ["-l", caption_languages]

    concurrent_downloads_value = options.get("concurrent_downloads") or options.get("concurrent")
    if concurrent_downloads_value:
        arg_list += ["--concurrent-downloads", str(concurrent_downloads_value)]

    browser_value = options.get("browser")
    if browser_value:
        arg_list += ["--browser", browser_value]

    h265_crf = options.get("h265_crf")
    if h265_crf:
        arg_list += ["--h265-crf", str(h265_crf)]
    h265_preset = options.get("h265_preset")
    if h265_preset:
        arg_list += ["--h265-preset", str(h265_preset)]

    if options.get("download_captions"):
        arg_list.append("--download-captions")
    if options.get("download_assets"):
        arg_list.append("--download-assets")
    if options.get("download_quizzes"):
        arg_list.append("--download-quizzes")
    if options.get("keep_vtt"):
        arg_list.append("--keep-vtt")
    if options.get("skip_lectures"):
        arg_list.append("--skip-lectures")
    if options.get("skip_hls"):
        arg_list.append("--skip-hls")
    if options.get("id_as_course_name"):
        arg_list.append("--id-as-course-name")
    if options.get("subscription_course"):
        arg_list.append("--subscription-course")
    if options.get("save_to_file"):
        arg_list.append("--save-to-file")
    if options.get("load_from_file"):
        arg_list.append("--load-from-file")
    if options.get("continue_lecture_numbers"):
        arg_list.append("--continue-lecture-numbers")
    if options.get("use_h265"):
        arg_list.append("--use-h265")
    if options.get("use_nvenc"):
        arg_list.append("--use-nvenc")

    try:
        sys.argv = arg_list
        pre_run()
    finally:
        sys.argv = original_argv

# Import from main.py
import main
from main import (
    Udemy, pre_run, logger, parse_new, _print_course_info, 
    bearer_token, portal_name, course_name, course_url, info,
    dl_assets, dl_captions, dl_quizzes, skip_lectures, caption_locale,
    quality, keep_vtt, skip_hls, concurrent_downloads, save_to_file,
    load_from_file, id_as_course_name, is_subscription_course,
    use_h265, h265_crf, h265_preset, use_nvenc, browser,
    use_continuous_lecture_numbers, chapter_filter, lecture_filter,
    DOWNLOAD_DIR, sanitize_filename
)


def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Print CLI header"""
    print("=" * 80)
    print("🎓 UDEMY COURSE DOWNLOADER - INTERACTIVE CLI VERSION")
    print("=" * 80)
    print()


def print_section_header(title: str):
    """Print section header"""
    print(f"\n{'─' * 60}")
    print(f"📋 {title}")
    print("─" * 60)


def get_user_input(prompt: str, default: str = "", required: bool = False) -> str:
    """Get user input with optional default value"""
    if default:
        display_prompt = f"{prompt} [{default}]: "
    else:
        display_prompt = f"{prompt}: "
    
    while True:
        value = input(display_prompt).strip()
        if not value and default:
            return default
        if not value and required:
            print("❌ This field is required. Please enter a value.")
            continue
        return value


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json"""
    config_path = "config.json"
    default_config = {
        "course_url": "",
        "token": "",
        "udemy_type": "normal",
        "chapter": "",
        "lecture": "",
        "quality": "",
        "lang": "en,ar",
        "concurrent": "10",
        "out_dir": "",
        "loglevel": "",
        "browser": "",
        "h265_crf": "",
        "h265_preset": "",
        "decryption_key": "",
        "use_h265": False,
        "use_nvenc": False,
        "download_captions": True,
        "download_assets": True,
        "download_quizzes": False,
        "keep_vtt": False,
        "skip_lectures": False,
        "skip_hls": False,
        "info": False,
        "id_as_course_name": False,
        "subscription_course": False,
        "save_to_file": False,
        "load_from_file": False,
        "continue_lecture_numbers": False,
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                # Merge with defaults to ensure all keys exist
                for key, value in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = value
                return loaded_config
        except Exception as e:
            print(f"⚠️  Error loading config.json: {e}")
            print("   Using default configuration")
    
    return default_config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json"""
    config_path = "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Configuration saved to {config_path}")
    except Exception as e:
        print(f"⚠️  Error saving config: {e}")


def get_yes_no(prompt: str, default: bool = False) -> bool:
    """Get yes/no input from user"""
    default_str = "Y/n" if default else "y/N"
    while True:
        response = input(f"{prompt} [{default_str}]: ").strip().lower()
        if not response:
            return default
        if response in ['y', 'yes']:
            return True
        if response in ['n', 'no']:
            return False
        print("❌ Please enter 'y' for yes or 'n' for no.")


def get_number_input(prompt: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    """Get numeric input from user"""
    while True:
        if default is not None:
            display_prompt = f"{prompt} [{default}]: "
        else:
            display_prompt = f"{prompt}: "
        
        response = input(display_prompt).strip()
        if not response and default is not None:
            return default
        
        try:
            value = int(response)
            if min_val is not None and value < min_val:
                print(f"❌ Value must be at least {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"❌ Value must be at most {max_val}")
                continue
            return value
        except ValueError:
            print("❌ Please enter a valid number.")


def select_chapters_interactive(chapters: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """Interactive chapter and video selection"""
    print_section_header("CHAPTER & VIDEO SELECTION")
    
    # Display all chapters
    print("📚 Available Chapters:")
    print()
    for i, chapter in enumerate(chapters, 1):
        chapter_title = chapter.get('title', f'Chapter {i}')
        video_count = len(chapter.get('videos', []))
        print(f"  {i:2d}. {chapter_title} ({video_count} videos)")
    
    print(f"\n📊 Total: {len(chapters)} chapters, {sum(len(ch.get('videos', [])) for ch in chapters)} videos")
    
    # Chapter selection options
    print("\n🎯 Chapter Selection Options:")
    print("  1. All chapters")
    print("  2. Specific chapters")
    print("  3. Range of chapters")
    print("  4. Interactive chapter-by-chapter selection")
    
    while True:
        choice = get_number_input("\nSelect option", min_val=1, max_val=4)
        
        if choice == 1:
            # All chapters
            selected_pairs = []
            for chapter in chapters:
                chapter_id = chapter.get('id', chapter.get('title'))
                for video in chapter.get('videos', []):
                    selected_pairs.append((chapter_id, video.get('id')))
            print(f"✅ Selected all chapters ({len(selected_pairs)} videos)")
            return selected_pairs
            
        elif choice == 2:
            # Specific chapters
            print("\n📝 Enter chapter numbers separated by commas (e.g., 1,3,5,7)")
            chapter_input = get_user_input("Chapter numbers", required=True)
            selected_chapters = parse_chapter_numbers(chapter_input, len(chapters))
            if selected_chapters:
                return select_videos_from_chapters(chapters, selected_chapters)
            
        elif choice == 3:
            # Range of chapters
            start = get_number_input("Start chapter", min_val=1, max_val=len(chapters))
            end = get_number_input("End chapter", default=len(chapters), min_val=start, max_val=len(chapters))
            selected_chapters = list(range(start, end + 1))
            return select_videos_from_chapters(chapters, selected_chapters)
            
        elif choice == 4:
            # Interactive selection
            return interactive_chapter_video_selection(chapters)


def parse_chapter_numbers(input_str: str, max_chapters: int) -> List[int]:
    """Parse chapter numbers from user input"""
    try:
        selected = []
        for part in input_str.split(','):
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                selected.extend(range(start, end + 1))
            else:
                selected.append(int(part))
        
        # Validate ranges
        valid_selected = [ch for ch in selected if 1 <= ch <= max_chapters]
        if len(valid_selected) != len(selected):
            print(f"⚠️  Some chapter numbers were invalid. Using: {valid_selected}")
        
        return sorted(list(set(valid_selected)))
    except ValueError:
        print("❌ Invalid format. Please use numbers and ranges like: 1,3,5-8,10")
        return []


def select_videos_from_chapters(chapters: List[Dict[str, Any]], selected_chapter_nums: List[int]) -> List[Tuple[int, int]]:
    """Select videos from specific chapters"""
    print(f"\n🎬 Video Selection for {len(selected_chapter_nums)} chapters:")
    print("  1. All videos from selected chapters")
    print("  2. Select specific videos from each chapter")
    
    choice = get_number_input("Select option", default=1, min_val=1, max_val=2)
    
    selected_pairs = []
    
    if choice == 1:
        # All videos from selected chapters
        for chapter_num in selected_chapter_nums:
            chapter = chapters[chapter_num - 1]
            chapter_id = chapter.get('id', chapter.get('title'))
            for video in chapter.get('videos', []):
                selected_pairs.append((chapter_id, video.get('id')))
        print(f"✅ Selected all videos from {len(selected_chapter_nums)} chapters ({len(selected_pairs)} videos)")
        
    else:
        # Interactive video selection per chapter
        for chapter_num in selected_chapter_nums:
            chapter = chapters[chapter_num - 1]
            chapter_title = chapter.get('title', f'Chapter {chapter_num}')
            videos = chapter.get('videos', [])
            
            print(f"\n📂 Chapter {chapter_num}: {chapter_title}")
            print(f"   Available videos: {len(videos)}")
            
            if not videos:
                continue
                
            # Show videos
            for i, video in enumerate(videos, 1):
                video_title = video.get('title', f'Video {i}')
                video_type = video.get('type', 'video')
                has_assets = video.get('has_assets', False)
                asset_type = video.get('asset_type', '')
                
                # Add icons based on type
                if video_type == "quiz":
                    icon = "📝 "
                elif video_type == "file":
                    if asset_type == "article":
                        icon = "📄 "
                    elif asset_type in ["e-book", "ebook"]:
                        icon = "📚 "
                    elif asset_type == "presentation":
                        icon = "📊 "
                    elif asset_type == "audio":
                        icon = "🎵 "
                    else:
                        icon = "📁 "
                else:  # video
                    if has_assets:
                        icon = "📎 "
                    else:
                        icon = "🎥 "
                
                print(f"     {i:2d}. {icon}{video_title}")
            
            print("\n   Options:")
            print("     1. All videos from this chapter")
            print("     2. Specific videos")
            print("     3. Skip this chapter")
            
            video_choice = get_number_input("   Select", default=1, min_val=1, max_val=3)
            
            if video_choice == 1:
                # All videos
                chapter_id = chapter.get('id', chapter.get('title'))
                for video in videos:
                    selected_pairs.append((chapter_id, video.get('id')))
                print(f"   ✅ Added all {len(videos)} videos from this chapter")
                
            elif video_choice == 2:
                # Specific videos
                video_input = get_user_input("   Video numbers (e.g., 1,3,5-7)")
                if video_input:
                    selected_video_nums = parse_chapter_numbers(video_input, len(videos))
                    chapter_id = chapter.get('id', chapter.get('title'))
                    for video_num in selected_video_nums:
                        video = videos[video_num - 1]
                        selected_pairs.append((chapter_id, video.get('id')))
                    print(f"   ✅ Added {len(selected_video_nums)} videos from this chapter")
            else:
                print("   ⏭️  Skipped this chapter")
    
    return selected_pairs


def interactive_chapter_video_selection(chapters: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """Full interactive selection chapter by chapter"""
    selected_pairs = []
    
    print("\n🔍 Interactive Chapter-by-Chapter Selection")
    print("You'll be asked about each chapter individually.")
    
    for i, chapter in enumerate(chapters, 1):
        chapter_title = chapter.get('title', f'Chapter {i}')
        videos = chapter.get('videos', [])
        
        print(f"\n📂 Chapter {i}/{len(chapters)}: {chapter_title}")
        print(f"   📹 {len(videos)} videos available")
        
        if not get_yes_no(f"   Include this chapter?", default=True):
            print("   ⏭️  Skipped")
            continue
        
        # Chapter included, now select videos
        if len(videos) <= 5:
            # Small chapter, show all videos
            print("   Videos:")
            for j, video in enumerate(videos, 1):
                video_title = video.get('title', f'Video {j}')
                video_type = video.get('type', 'video')
                has_assets = video.get('has_assets', False)
                asset_type = video.get('asset_type', '')
                
                # Add icons based on type
                if video_type == "quiz":
                    icon = "📝 "
                elif video_type == "file":
                    if asset_type == "article":
                        icon = "📄 "
                    elif asset_type in ["e-book", "ebook"]:
                        icon = "📚 "
                    elif asset_type == "presentation":
                        icon = "📊 "
                    elif asset_type == "audio":
                        icon = "🎵 "
                    else:
                        icon = "📁 "
                else:  # video
                    if has_assets:
                        icon = "📎 "
                    else:
                        icon = "🎥 "
                
                print(f"     {j}. {icon}{video_title}")
            
            if get_yes_no("   Include all videos?", default=True):
                chapter_id = chapter.get('id', chapter.get('title'))
                for video in videos:
                    selected_pairs.append((chapter_id, video.get('id')))
                print(f"   ✅ Added all {len(videos)} videos")
            else:
                # Manual selection for small chapter
                video_input = get_user_input("   Select videos (e.g., 1,3,5)")
                if video_input:
                    selected_video_nums = parse_chapter_numbers(video_input, len(videos))
                    chapter_id = chapter.get('id', chapter.get('title'))
                    for video_num in selected_video_nums:
                        video = videos[video_num - 1]
                        selected_pairs.append((chapter_id, video.get('id')))
                    print(f"   ✅ Added {len(selected_video_nums)} videos")
        else:
            # Large chapter, offer bulk options
            if get_yes_no("   Include all videos?", default=True):
                chapter_id = chapter.get('id', chapter.get('title'))
                for video in videos:
                    selected_pairs.append((chapter_id, video.get('id')))
                print(f"   ✅ Added all {len(videos)} videos")
            else:
                print("   🔍 Custom selection for large chapter:")
                print("     1. First half")
                print("     2. Second half") 
                print("     3. Specific videos")
                print("     4. Skip chapter")
                
                video_choice = get_number_input("   Select", default=1, min_val=1, max_val=4)
                chapter_id = chapter.get('id', chapter.get('title'))
                
                if video_choice == 1:
                    # First half
                    half = len(videos) // 2
                    for video in videos[:half]:
                        selected_pairs.append((chapter_id, video.get('id')))
                    print(f"   ✅ Added first {half} videos")
                elif video_choice == 2:
                    # Second half
                    half = len(videos) // 2
                    for video in videos[half:]:
                        selected_pairs.append((chapter_id, video.get('id')))
                    print(f"   ✅ Added last {len(videos) - half} videos")
                elif video_choice == 3:
                    # Show first few and last few videos for reference
                    print("   📋 Sample videos (showing first 5 and last 5):")
                    for j, video in enumerate(videos[:5], 1):
                        video_title = video.get('title', f'Video {j}')
                        video_type = video.get('type', 'video')
                        has_assets = video.get('has_assets', False)
                        asset_type = video.get('asset_type', '')
                        
                        # Add icons based on type
                        if video_type == "quiz":
                            icon = "📝 "
                        elif video_type == "file":
                            if asset_type == "article":
                                icon = "📄 "
                            elif asset_type in ["e-book", "ebook"]:
                                icon = "📚 "
                            elif asset_type == "presentation":
                                icon = "📊 "
                            elif asset_type == "audio":
                                icon = "🎵 "
                            else:
                                icon = "📁 "
                        else:  # video
                            if has_assets:
                                icon = "📎 "
                            else:
                                icon = "🎥 "
                        
                        print(f"     {j:2d}. {icon}{video_title}")
                    if len(videos) > 10:
                        print("     ...")
                        for j, video in enumerate(videos[-5:], len(videos)-4):
                            video_title = video.get('title', f'Video {j}')
                            video_type = video.get('type', 'video')
                            has_assets = video.get('has_assets', False)
                            asset_type = video.get('asset_type', '')
                            
                            # Add icons based on type
                            if video_type == "quiz":
                                icon = "📝 "
                            elif video_type == "file":
                                if asset_type == "article":
                                    icon = "📄 "
                                elif asset_type in ["e-book", "ebook"]:
                                    icon = "📚 "
                                elif asset_type == "presentation":
                                    icon = "📊 "
                                elif asset_type == "audio":
                                    icon = "🎵 "
                                else:
                                    icon = "📁 "
                            else:  # video
                                if has_assets:
                                    icon = "📎 "
                                else:
                                    icon = "🎥 "
                            
                            print(f"     {j:2d}. {icon}{video_title}")
                    
                    video_input = get_user_input("   Select videos (e.g., 1-5,10,15-20)")
                    if video_input:
                        selected_video_nums = parse_chapter_numbers(video_input, len(videos))
                        for video_num in selected_video_nums:
                            video = videos[video_num - 1]
                            selected_pairs.append((chapter_id, video.get('id')))
                        print(f"   ✅ Added {len(selected_video_nums)} videos")
                else:
                    print("   ⏭️  Skipped chapter")
    
    print(f"\n🎉 Selection complete! Total: {len(selected_pairs)} videos selected from {len(chapters)} chapters")
    return selected_pairs


def get_course_information(config: Dict[str, Any]) -> Dict[str, str]:
    """Get course information from user with config defaults"""
    print_section_header("COURSE INFORMATION")
    
    course_info = {}
    
    # Course URL
    course_info['course_url'] = get_user_input(
        "📚 Course URL", 
        default=config.get('course_url', ''), 
        required=True
    )
    
    # Bearer Token
    course_info['token'] = get_user_input(
        "🔑 Bearer Token", 
        default=config.get('token', ''), 
        required=True
    )
    
    # Udemy Type
    print("\n🌐 Udemy Type:")
    print("  1. Normal Udemy (www.udemy.com)")
    print("  2. Udemy Business (enterprise)")
    
    udemy_type_default = config.get('udemy_type', 'normal')
    default_choice = 1 if udemy_type_default == 'normal' else 2
    
    while True:
        choice = get_number_input("Select Udemy type", default=default_choice, min_val=1, max_val=2)
        if choice == 1:
            course_info['udemy_type'] = 'normal'
            break
        elif choice == 2:
            course_info['udemy_type'] = 'business'
            break
    
    # Decryption Key
    course_info['decryption_key'] = get_user_input(
        "🔐 Decryption Key", 
        default=config.get('decryption_key', ''), 
        required=True
    )
    
    return course_info


def get_download_options(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get download options from user with config defaults"""
    print_section_header("DOWNLOAD OPTIONS")
    
    options = {}
    
    # Chapter selection
    chapter_input = get_user_input(
        "📚 Chapter (e.g. 1,3-5)", 
        default=config.get('chapter', '')
    )
    options['chapter'] = chapter_input
    
    # Lecture selection
    lecture_input = get_user_input(
        "🎬 Video (e.g. 1,3-5)", 
        default=config.get('lecture', '')
    )
    options['lecture'] = lecture_input
    
    # Quality
    quality_input = get_user_input(
        "🎥 Quality (e.g. 720)", 
        default=config.get('quality', '')
    )
    if quality_input:
        try:
            options['quality'] = int(quality_input)
        except ValueError:
            print("⚠️  Invalid quality, using best available")
    
    # Caption languages - ENHANCED SUPPORT
    print("\n🌐 Caption Languages:")
    print("  Available options:")
    print("    • en - English")
    print("    • ar - Arabic")  
    print("    • en,ar - Both English and Arabic")
    print("    • all - All available languages")
    print("    • (empty) - No captions")
    
    caption_input = get_user_input(
        "Caption languages", 
        default=config.get('lang', 'en,ar')
    )
    if caption_input:
        options['caption_languages'] = caption_input
        options['download_captions'] = config.get('download_captions', True)
    else:
        options['download_captions'] = False
    
    # Concurrent downloads
    concurrent_input = get_user_input(
        "⚡ Concurrent Downloads", 
        default=config.get('concurrent', '10')
    )
    try:
        options['concurrent_downloads'] = int(concurrent_input)
    except ValueError:
        options['concurrent_downloads'] = 10
    
    # Output directory
    output_dir = get_user_input(
        "📁 Output Directory", 
        default=config.get('out_dir', '') or os.path.join(os.getcwd(), "out_dir")
    )
    options['output_dir'] = output_dir
    
    # Log level
    loglevel_input = get_user_input(
        "📝 Log Level", 
        default=config.get('loglevel', '')
    )
    options['loglevel'] = loglevel_input
    
    # Browser
    browser_input = get_user_input(
        "🌐 Browser (for cookies)", 
        default=config.get('browser', '')
    )
    options['browser'] = browser_input
    
    # Download options
    print("\n📥 Download Options:")
    options['download_assets'] = get_yes_no(
        "Download course assets (PDFs, files, etc.)", 
        default=config.get('download_assets', True)
    )
    options['download_quizzes'] = get_yes_no(
        "Download quizzes", 
        default=config.get('download_quizzes', False)
    )
    
    # Advanced options
    print("\n⚙️  Advanced Options:")
    if get_yes_no("Configure advanced options?", default=False):
        options['use_h265'] = get_yes_no(
            "Use H.265 encoding", 
            default=config.get('use_h265', False)
        )
        if options['use_h265']:
            options['use_nvenc'] = get_yes_no(
                "Use NVIDIA hardware encoding", 
                default=config.get('use_nvenc', False)
            )
            options['h265_crf'] = get_user_input(
                "H.265 CRF", 
                default=config.get('h265_crf', '')
            )
            options['h265_preset'] = get_user_input(
                "H.265 Preset", 
                default=config.get('h265_preset', '')
            )
        
        options['keep_vtt'] = get_yes_no(
            "Keep VTT subtitle files", 
            default=config.get('keep_vtt', False)
        )
        options['skip_hls'] = get_yes_no(
            "Skip HLS streams", 
            default=config.get('skip_hls', False)
        )
        options['skip_lectures'] = get_yes_no(
            "Skip lectures", 
            default=config.get('skip_lectures', False)
        )
        options['id_as_course_name'] = get_yes_no(
            "Use ID as course name", 
            default=config.get('id_as_course_name', False)
        )
        options['subscription_course'] = get_yes_no(
            "Subscription course", 
            default=config.get('subscription_course', False)
        )
        options['save_to_file'] = get_yes_no(
            "Save to file", 
            default=config.get('save_to_file', False)
        )
        options['load_from_file'] = get_yes_no(
            "Load from file", 
            default=config.get('load_from_file', False)
        )
        options['continue_lecture_numbers'] = get_yes_no(
            "Continue lecture numbers", 
            default=config.get('continue_lecture_numbers', False)
        )
    else:
        # Use config defaults for advanced options
        options['use_h265'] = config.get('use_h265', False)
        options['use_nvenc'] = config.get('use_nvenc', False)
        options['h265_crf'] = config.get('h265_crf', '')
        options['h265_preset'] = config.get('h265_preset', '')
        options['keep_vtt'] = config.get('keep_vtt', False)
        options['skip_hls'] = config.get('skip_hls', False)
        options['skip_lectures'] = config.get('skip_lectures', False)
        options['id_as_course_name'] = config.get('id_as_course_name', False)
        options['subscription_course'] = config.get('subscription_course', False)
        options['save_to_file'] = config.get('save_to_file', False)
        options['load_from_file'] = config.get('load_from_file', False)
        options['continue_lecture_numbers'] = config.get('continue_lecture_numbers', False)
    
    return options


def display_selection_summary(selected_pairs: List[Tuple[int, int]], chapters: List[Dict[str, Any]], options: Dict[str, Any]):
    """Display selection summary"""
    print_section_header("DOWNLOAD SUMMARY")
    
    # Count videos per chapter
    chapter_counts = {}
    for chapter_id, video_id in selected_pairs:
        chapter_counts[chapter_id] = chapter_counts.get(chapter_id, 0) + 1
    
    print(f"📊 Selected Content:")
    print(f"   • {len(chapter_counts)} chapters")
    print(f"   • {len(selected_pairs)} videos")
    
    if len(chapter_counts) <= 10:  # Show details for small selections
        print(f"\n📂 Chapters:")
        for chapter in chapters:
            chapter_id = chapter.get('id', chapter.get('title'))
            if chapter_id in chapter_counts:
                chapter_title = chapter.get('title', str(chapter_id))
                video_count = chapter_counts[chapter_id]
                total_videos = len(chapter.get('videos', []))
                print(f"   • {chapter_title}: {video_count}/{total_videos} videos")
    
    print(f"\n⚙️  Options:")
    if options.get('quality'):
        print(f"   • Quality: {options['quality']}p")
    else:
        print(f"   • Quality: Best available")
    
    if options.get('download_captions'):
        caption_langs = options.get('caption_languages', 'en')
        print(f"   • Captions: {caption_langs}")
    else:
        print(f"   • Captions: None")
    
    if options.get('download_assets'):
        print(f"   • Assets: Yes")
    
    if options.get('download_quizzes'):
        print(f"   • Quizzes: Yes")
    
    estimated_time = len(selected_pairs) * 2  # Rough estimate: 2 minutes per video
    if estimated_time > 60:
        hours = estimated_time // 60
        minutes = estimated_time % 60
        print(f"\n⏱️  Estimated time: ~{hours}h {minutes}m")
    else:
        print(f"\n⏱️  Estimated time: ~{estimated_time}m")


def parse_new_cli(udemy: 'Udemy', udemy_object: dict, selected_pairs: List[Tuple[int, int]]) -> None:
    """
    CLI version of parse_new that processes only selected videos
    
    Args:
        udemy: Udemy client instance
        udemy_object: Course data structure
        selected_pairs: List of (chapter_id, video_id) tuples to download
    """
    from pathvalidate import sanitize_filename
    
    # Convert selected pairs to a set for faster lookup
    selected_video_ids = set(vid for chap, vid in selected_pairs)
    
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

    total_chapters = udemy_object.get("total_chapters")
    total_lectures = len(selected_pairs)  # Only count selected videos
    
    logger.info(f"Chapter(s) ({total_chapters})")
    logger.info(f"Selected Lecture(s) ({total_lectures})")
    print(f"GUI_PROGRESS:TOTAL_LECTURES:{total_lectures}", flush=True)
    
    if id_to_title_map:
        map_file_path = os.path.join(course_dir, "id_to_title.json")
        try:
            with open(map_file_path, "w", encoding="utf-8") as f:
                json.dump(id_to_title_map, f, indent=2, ensure_ascii=False)
            logger.info(f"> Saved lecture ID to title mapping at {map_file_path}")
        except Exception as e:
            logger.error(f"> Error saving ID to title mapping: {e}")

    processed_lectures = 0
    
    for chapter in udemy_object.get("chapters"):
        current_chapter_index = int(chapter.get("chapter_index"))
        
        # Skip chapters not in the filter if a filter is provided
        if chapter_filter is not None and current_chapter_index not in chapter_filter:
            logger.info("Skipping chapter %s as it is not in the specified filter", current_chapter_index)
            continue

        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        
        # Check if this chapter has any selected videos
        chapter_has_selected_videos = any(
            lecture.get("id") in selected_video_ids 
            for lecture in chapter.get("lectures", [])
        )
        
        if not chapter_has_selected_videos:
            logger.info(f"Skipping chapter {chapter_index} - no videos selected")
            continue
            
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
                from main import process_quiz
                process_quiz(udemy, lecture, chapter_dir)
                continue

            index = lecture.get("index")  # this is lecture_counter
            lecture_title = lecture.get("lecture_title")
            parsed_lecture = udemy._parse_lecture(lecture)

            lecture_extension = parsed_lecture.get("extension")
            extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
            if lecture_extension != None:
                # if the lecture extension property isnt none, set the extension to the lecture extension
                extension = lecture_extension
                
            from main import deEmojify
            lecture_file_name = sanitize_filename(lecture_title + "." + extension)
            lecture_file_name = deEmojify(lecture_file_name)
            lecture_path = os.path.join(chapter_dir, lecture_file_name)

            if not skip_lectures:
                processed_lectures += 1
                logger.info(f"  > Processing lecture {processed_lectures} of {total_lectures}")
                
                # Report current lecture progress for GUI
                print(f"GUI_PROGRESS:COMPLETED_LECTURE:{processed_lectures}", flush=True)

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
                        from main import process_lecture
                        process_lecture(parsed_lecture, lecture_path, chapter_dir)

            # download subtitles for this lecture
            subtitles = parsed_lecture.get("subtitles")
            if dl_captions and subtitles != None and lecture_extension == None:
                logger.info("Processing {} caption(s)...".format(len(subtitles)))
                
                # Track which languages we're downloading
                downloading_languages = []
                
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    from main import should_download_caption, process_caption
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
                            from main import download_aria
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

    logger.info(f"Processed {processed_lectures} selected lectures from {len(udemy_object.get('chapters', []))} chapters")


def run_download_process(course_info: Dict[str, str], selected_pairs: List[Tuple[int, int]], 
                        options: Dict[str, Any]) -> bool:
    """Run the actual download process"""
    print_section_header("STARTING DOWNLOAD")
    
    # Set global variables for main.py
    global dl_assets, dl_captions, dl_quizzes, skip_lectures, caption_locale
    global quality, keep_vtt, skip_hls, concurrent_downloads, use_h265, use_nvenc
    global DOWNLOAD_DIR, portal_name, id_as_course_name, is_subscription_course
    global use_continuous_lecture_numbers, chapter_filter, lecture_filter
    global save_to_file, load_from_file, browser
    
    # Apply options
    dl_assets = options.get('download_assets', False)
    dl_captions = options.get('download_captions', False)
    dl_quizzes = options.get('download_quizzes', False)
    skip_lectures = options.get('skip_lectures', False)
    caption_locale = options.get('caption_languages', 'en')
    quality = options.get('quality')
    keep_vtt = options.get('keep_vtt', False)
    skip_hls = options.get('skip_hls', False)
    concurrent_downloads = options.get('concurrent_downloads', 10)
    use_h265 = options.get('use_h265', False)
    use_nvenc = options.get('use_nvenc', False)
    id_as_course_name = options.get('id_as_course_name', False)
    is_subscription_course = options.get('subscription_course', False)
    use_continuous_lecture_numbers = options.get('continue_lecture_numbers', False)
    save_to_file = options.get('save_to_file', False)
    load_from_file = options.get('load_from_file', False)
    browser = options.get('browser') or None
    
    # Parse chapter and lecture filters
    chapter_filter = None
    if options.get('chapter'):
        chapter_filter = parse_chapter_numbers(options['chapter'], 1000)  # Large number for unknown max
    
    lecture_filter = None
    if options.get('lecture'):
        lecture_filter = parse_chapter_numbers(options['lecture'], 1000)  # Large number for unknown max
    
    # Set output directory
    DOWNLOAD_DIR = options.get('output_dir', os.path.join(os.getcwd(), "out_dir"))
    
    try:
        # Initialize Udemy client
        udemy = Udemy(course_info['token'])
        
        print("🔍 Fetching course information...")
        course_id, course_info_data = udemy._extract_course_info(course_info['course_url'])
        
        print("📚 Fetching course curriculum...")
        course_json = udemy._extract_course_curriculum(course_info['course_url'], course_id, portal_name)
        course_json["portal_name"] = portal_name
        
        print("📝 Processing course data...")
        
        # Build udemy_object similar to main.py
        udemy_object = {}
        udemy_object["bearer_token"] = course_info['token']
        udemy_object["course_id"] = course_id
        udemy_object["title"] = course_info_data.get('title')
        udemy_object["course_title"] = course_info_data.get('published_title')
        udemy_object["chapters"] = []
        chapter_index_counter = -1

        course = course_json.get("results")
        if course:
            print("🔄 Building course structure...")
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
                    from pathvalidate import sanitize_filename
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
                        from pathvalidate import sanitize_filename
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
                        lecture_index = entry.get("object_index")
                        from pathvalidate import sanitize_filename
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
                        from pathvalidate import sanitize_filename
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
                        lecture_index = entry.get("object_index")
                        from pathvalidate import sanitize_filename
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
            
            print(f"✅ Course loaded: {total_chapters} chapters, {total_lectures} lectures")
            
            if total_chapters > 100 or total_lectures > 500:
                print(f"⚠️  This is a large course: {total_chapters} chapters, {total_lectures} lectures")
                print("💡 Consider using --save-to-file for better performance with large courses")

        # Process selected content using CLI parser
        print("🚀 Starting download process...")
        parse_new_cli(udemy, udemy_object, selected_pairs)
        
        print("✅ Download process completed successfully")
        
        # Clean up any remaining .part files and empty subtitle files after the download process
        print("🧹 Cleaning up temporary files...")
        from main import cleanup_part_files_in_directory, cleanup_empty_subtitle_files
        cleanup_part_files_in_directory(DOWNLOAD_DIR)
        cleanup_empty_subtitle_files(DOWNLOAD_DIR)
        
        return True
        
    except Exception as e:
        print(f"❌ Error during download: {e}")
        logger.exception("CLI download error")
        return False


def main():
    """Main CLI function"""
    original_argv = sys.argv[:]

    clear_screen()
    print_header()
    
    # Load configuration
    print("📋 Loading configuration...")
    config = load_config()

    overrides = parse_cli_overrides()
    if overrides:
        for key, value in overrides.items():
            config[key] = value
        applied_keys = ", ".join(sorted(overrides.keys()))
        print(f"⚙️  Applied command-line overrides for: {applied_keys}")
    
    # Get course information with config defaults
    course_info = get_course_information(config)
    
    # Get download options with config defaults
    options = get_download_options(config)
    
    # Save updated configuration
    print("\n💾 Saving configuration...")
    updated_config = {
        **config,
        **course_info,
        **options
    }
    save_config(updated_config)
    
    try:
        initialize_main_environment(course_info, options, original_argv)

        # Initialize Udemy client
        print("\n🔍 Connecting to Udemy...")
        udemy = Udemy(course_info['token'])
        
        print("📖 Fetching course information...")
        course_id, course_info_data = udemy._extract_course_info(course_info['course_url'])
        
        if not course_info_data:
            print("❌ Could not fetch course information. Please check your URL and token.")
            return 1
        
        course_title = course_info_data.get('published_title', 'Unknown Course')
        print(f"✅ Found course: {course_title}")
        
        print("📚 Fetching course curriculum...")
        course_json = udemy._extract_course_curriculum(course_info['course_url'], course_id, portal_name)
        
        # Build chapters structure for selection (simplified)
        print("📝 Processing course structure...")
        chapters_for_gui = []
        
        # This is a simplified version - in full implementation, we'd need to
        # properly parse the course structure like in main.py
        course = course_json.get("results", [])
        current_chapter = None
        
        for entry in course:
            clazz = entry.get("_class")
            
            if clazz == "chapter":
                if current_chapter:
                    chapters_for_gui.append(current_chapter)
                
                current_chapter = {
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                    "videos": []
                }
            
            elif clazz in ["lecture", "quiz"] and current_chapter:
                # Check if this is a file-type lecture
                asset_type = None
                asset = entry.get("asset", {})
                if isinstance(asset, dict):
                    asset_type = asset.get("asset_type", "").lower()
                
                lecture_type = "quiz" if clazz == "quiz" else "video"
                if asset_type in ["article", "file", "e-book", "ebook", "presentation", "audio"]:
                    lecture_type = "file"
                
                # Check for supplementary assets
                has_assets = False
                supp_assets = entry.get("supplementary_assets", [])
                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                    has_assets = True
                
                current_chapter["videos"].append({
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                    "thumbnail_url": None,
                    "type": lecture_type,
                    "has_assets": has_assets,
                    "asset_type": asset_type
                })
        
        # Add the last chapter
        if current_chapter:
            chapters_for_gui.append(current_chapter)
        
        if not chapters_for_gui:
            print("❌ No chapters found in course.")
            return 1
        
        print(f"✅ Course structure loaded: {len(chapters_for_gui)} chapters")
        
        # Interactive chapter selection
        selected_pairs = select_chapters_interactive(chapters_for_gui)
        
        if not selected_pairs:
            print("❌ No content selected for download.")
            return 1
        
        # Display summary
        display_selection_summary(selected_pairs, chapters_for_gui, options)
        
        # Confirm download
        print(f"\n" + "="*60)
        if not get_yes_no("🚀 Start download?", default=True):
            print("❌ Download cancelled by user.")
            return 0
        
        # Run download
        success = run_download_process(course_info, selected_pairs, options)
        
        if success:
            print(f"\n🎉 Download completed successfully!")
            print(f"📁 Files saved to: {options.get('output_dir', 'out_dir')}")
            return 0
        else:
            print(f"\n❌ Download failed. Check the logs for details.")
            return 1
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Download interrupted by user.")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logger.exception("CLI main error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
