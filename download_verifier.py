# -*- coding: utf-8 -*-
"""
Download Verification Module
Verifies downloaded course files against the id_to_title.json manifest
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathvalidate import sanitize_filename

logger = logging.getLogger(__name__)


def is_file_complete(file_path: str) -> bool:
    """
    Check if a file is complete (not empty, not a .part file)
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        True if file exists, is not empty, and is not a partial download
    """
    if not os.path.exists(file_path):
        return False
    
    # Check if it's a .part file (incomplete download)
    if file_path.endswith('.part'):
        return False
    
    # Check if file size is greater than 0
    try:
        size = os.path.getsize(file_path)
        return size > 0
    except OSError:
        return False


def get_lecture_status(lecture_id: str, lecture_title: str, chapter_dir: str) -> Dict:
    """
    Check the download status of a specific lecture
    
    Args:
        lecture_id: The lecture ID
        lecture_title: The expected lecture title
        chapter_dir: Directory where the lecture should be located
        
    Returns:
        Dict with status information: {'status': str, 'file': str, 'size': int, 'reason': str}
        status can be: 'complete', 'incomplete', 'missing', 'encrypted_pending'
    """
    from main import deEmojify
    
    # Sanitize the title for filename matching
    sanitized_title = sanitize_filename(lecture_title)
    sanitized_title = deEmojify(sanitized_title)
    
    # Possible file extensions to check
    extensions = ['.mp4', '.mkv', '.webm', '.html', '.pdf', '.pptx', '.zip']
    
    result = {
        'status': 'missing',
        'file': None,
        'size': 0,
        'reason': 'File not found'
    }
    
    if not os.path.exists(chapter_dir):
        result['reason'] = f'Chapter directory does not exist: {chapter_dir}'
        return result
    
    # Check for encrypted files (pending decryption)
    encrypted_video = os.path.join(chapter_dir, f"{lecture_id}.encrypted.mp4")
    encrypted_audio = os.path.join(chapter_dir, f"{lecture_id}.encrypted.m4a")
    
    if os.path.exists(encrypted_video) or os.path.exists(encrypted_audio):
        result['status'] = 'encrypted_pending'
        result['file'] = f"{lecture_id}.encrypted.mp4" if os.path.exists(encrypted_video) else f"{lecture_id}.encrypted.m4a"
        result['reason'] = 'Encrypted file awaiting decryption'
        if os.path.exists(encrypted_video):
            result['size'] = os.path.getsize(encrypted_video)
        else:
            result['size'] = os.path.getsize(encrypted_audio)
        return result
    
    # Check for decrypted but not yet combined files
    decrypted_video = os.path.join(chapter_dir, f"{lecture_id}.mp4")
    decrypted_audio = os.path.join(chapter_dir, f"{lecture_id}.m4a")
    
    # Check for the final combined/renamed file (with title)
    for ext in extensions:
        expected_name = sanitized_title + ext
        final_file = os.path.join(chapter_dir, expected_name)
        
        # 1. Check exact match
        if os.path.exists(final_file):
            if is_file_complete(final_file):
                result['status'] = 'complete'
                result['file'] = os.path.basename(final_file)
                result['size'] = os.path.getsize(final_file)
                result['reason'] = 'Downloaded and renamed'
                return result
            else:
                result['status'] = 'incomplete'
                result['file'] = os.path.basename(final_file)
                result['size'] = os.path.getsize(final_file)
                result['reason'] = 'File exists but is empty or incomplete'
                return result
        
        # 2. Check for prefix match (e.g. "001 Title.mp4")
        # This is needed because main.py might add index prefixes to filenames
        try:
            for f in os.listdir(chapter_dir):
                if f.endswith(expected_name) and f != expected_name:
                    # Check if the prefix is likely an index (digits + space/dash/dot)
                    prefix = f[:-len(expected_name)]
                    # Simple heuristic: prefix should be short and contain digits
                    if len(prefix) < 10 and any(c.isdigit() for c in prefix):
                        full_path = os.path.join(chapter_dir, f)
                        if is_file_complete(full_path):
                            result['status'] = 'complete'
                            result['file'] = f
                            result['size'] = os.path.getsize(full_path)
                            result['reason'] = 'Downloaded (with prefix)'
                            return result
        except Exception:
            pass
    
    # Check for files with numeric ID (not yet renamed)
    for ext in extensions:
        id_file = os.path.join(chapter_dir, lecture_id + ext)
        if os.path.exists(id_file):
            if is_file_complete(id_file):
                result['status'] = 'complete'
                result['file'] = os.path.basename(id_file)
                result['size'] = os.path.getsize(id_file)
                result['reason'] = 'Downloaded (using ID, not renamed)'
                return result
            else:
                result['status'] = 'incomplete'
                result['file'] = os.path.basename(id_file)
                result['size'] = os.path.getsize(id_file)
                result['reason'] = 'File exists but is empty or incomplete'
                return result
    
    # Check for decrypted video/audio that needs combining
    if os.path.exists(decrypted_video) and os.path.exists(decrypted_audio):
        if is_file_complete(decrypted_video) and is_file_complete(decrypted_audio):
            result['status'] = 'complete'
            result['file'] = f"{lecture_id}.mp4 + {lecture_id}.m4a"
            result['size'] = os.path.getsize(decrypted_video) + os.path.getsize(decrypted_audio)
            result['reason'] = 'Decrypted but not yet combined'
            return result
    
    # Check for .part files (incomplete downloads)
    for ext in extensions:
        part_file = os.path.join(chapter_dir, sanitized_title + ext + '.part')
        if os.path.exists(part_file):
            result['status'] = 'incomplete'
            result['file'] = os.path.basename(part_file)
            result['size'] = os.path.getsize(part_file)
            result['reason'] = 'Download incomplete (.part file exists)'
            return result
    
    # File truly missing
    # Log what IS in the directory to help debugging
    try:
        files_in_dir = os.listdir(chapter_dir)
        logger.debug(f"Lecture {lecture_id} ({lecture_title}) missing. Files in {chapter_dir}: {files_in_dir}")
    except Exception:
        pass
        
    return result


def verify_chapter_downloads(chapter_dir: str, chapter_lectures: List[Dict], 
                            id_to_title_map: Dict[str, str]) -> Dict:
    """
    Verify downloads for a specific chapter
    
    Args:
        chapter_dir: Path to chapter directory
        chapter_lectures: List of lecture dicts with 'id' and 'lecture_title'
        id_to_title_map: Mapping of lecture IDs to titles
        
    Returns:
        Dict with verification results for this chapter
    """
    results = {
        'complete': [],
        'incomplete': [],
        'missing': [],
        'encrypted_pending': []
    }
    
    for lecture in chapter_lectures:
        lecture_id = str(lecture.get('id'))
        lecture_title = lecture.get('lecture_title') or id_to_title_map.get(lecture_id, lecture_id)
        
        status_info = get_lecture_status(lecture_id, lecture_title, chapter_dir)
        
        lecture_info = {
            'id': lecture_id,
            'title': lecture_title,
            'file': status_info['file'],
            'size': status_info['size'],
            'reason': status_info['reason']
        }
        
        # Categorize based on status
        if status_info['status'] == 'complete':
            results['complete'].append(lecture_info)
        elif status_info['status'] == 'incomplete':
            results['incomplete'].append(lecture_info)
        elif status_info['status'] == 'encrypted_pending':
            results['encrypted_pending'].append(lecture_info)
        else:  # missing
            results['missing'].append(lecture_info)
    
    return results


def verify_course_downloads(course_dir: str, id_to_title_map: Dict[str, str]) -> Dict:
    """
    Verify all downloads for a course against the id_to_title.json manifest
    
    Args:
        course_dir: Path to the course directory
        id_to_title_map: Mapping of lecture IDs to expected titles
        
    Returns:
        Dict with verification results including complete, incomplete, missing, and encrypted lectures
    """
    results = {
        'complete': [],
        'incomplete': [],
        'missing': [],
        'encrypted_pending': []
    }
    
    if not os.path.exists(course_dir):
        logger.error(f"Course directory does not exist: {course_dir}")
        return results
    
    # Iterate through all subdirectories (chapters)
    for item in os.listdir(course_dir):
        item_path = os.path.join(course_dir, item)
        
        # Skip files, only process directories (chapters)
        if not os.path.isdir(item_path):
            continue
        
        # Skip special directories
        if item in ['temp', 'logs', '.git']:
            continue
        
        chapter_dir = item_path
        logger.info(f"Verifying chapter: {item}")
        
        # Check all lectures that should be in this chapter
        # We need to scan for files and match them against the manifest
        for lecture_id, lecture_title in id_to_title_map.items():
            status_info = get_lecture_status(lecture_id, lecture_title, chapter_dir)
            
            # Only include lectures that have some presence in this chapter
            if status_info['status'] != 'missing':
                lecture_info = {
                    'id': lecture_id,
                    'title': lecture_title,
                    'file': status_info['file'],
                    'size': status_info['size'],
                    'reason': status_info['reason'],
                    'chapter': item
                }
                
                if status_info['status'] == 'complete':
                    results['complete'].append(lecture_info)
                elif status_info['status'] == 'incomplete':
                    results['incomplete'].append(lecture_info)
                elif status_info['status'] == 'encrypted_pending':
                    results['encrypted_pending'].append(lecture_info)
    
    # Find missing lectures (in manifest but not found anywhere)
    found_ids = set()
    for category in ['complete', 'incomplete', 'encrypted_pending']:
        found_ids.update(item['id'] for item in results[category])
    
    for lecture_id, lecture_title in id_to_title_map.items():
        if lecture_id not in found_ids:
            results['missing'].append({
                'id': lecture_id,
                'title': lecture_title,
                'file': None,
                'size': 0,
                'reason': 'Not found in any chapter directory'
            })
    
    return results


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.2f} {units[unit_index]}"


def generate_html_report(course_dir: str, course_name: str, verification_results: Dict) -> str:
    """
    Generate an HTML verification report
    
    Args:
        course_dir: Path to course directory
        course_name: Name of the course
        verification_results: Results from verify_course_downloads
        
    Returns:
        Path to the generated HTML report file
    """
    total_lectures = len(verification_results['complete']) + \
                    len(verification_results['incomplete']) + \
                    len(verification_results['missing']) + \
                    len(verification_results['encrypted_pending'])
    
    complete_count = len(verification_results['complete'])
    incomplete_count = len(verification_results['incomplete'])
    missing_count = len(verification_results['missing'])
    encrypted_count = len(verification_results['encrypted_pending'])
    
    success_rate = (complete_count / total_lectures * 100) if total_lectures > 0 else 0
    
    # Build HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download Verification Report - {course_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .complete {{ color: #28a745; }}
        .encrypted {{ color: #ffc107; }}
        .incomplete {{ color: #fd7e14; }}
        .missing {{ color: #dc3545; }}
        
        .success-rate {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
            font-size: 2em;
        }}
        
        .section {{
            padding: 30px;
        }}
        
        .section h2 {{
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        
        .lecture-list {{
            list-style: none;
        }}
        
        .lecture-item {{
            background: #f8f9fa;
            margin: 10px 0;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid;
            transition: all 0.2s;
        }}
        
        .lecture-item:hover {{
            background: #e9ecef;
            transform: translateX(5px);
        }}
        
        .lecture-item.complete {{ border-left-color: #28a745; }}
        .lecture-item.encrypted {{ border-left-color: #ffc107; }}
        .lecture-item.incomplete {{ border-left-color: #fd7e14; }}
        .lecture-item.missing {{ border-left-color: #dc3545; }}
        
        .lecture-title {{
            font-weight: 600;
            font-size: 1.1em;
            margin-bottom: 8px;
            color: #333;
        }}
        
        .lecture-details {{
            font-size: 0.9em;
            color: #666;
            display: grid;
            gap: 5px;
        }}
        
        .lecture-details span {{
            display: flex;
            gap: 10px;
        }}
        
        .label {{
            font-weight: 600;
            min-width: 80px;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            color: white;
        }}
        
        .badge.complete {{ background: #28a745; }}
        .badge.encrypted {{ background: #ffc107; color: #333; }}
        .badge.incomplete {{ background: #fd7e14; }}
        .badge.missing {{ background: #dc3545; }}
        
        .timestamp {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 0.9em;
            border-top: 1px solid #dee2e6;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #999;
            font-style: italic;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            .stat-card:hover, .lecture-item:hover {{
                transform: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Download Verification Report</h1>
            <div class="subtitle">{course_name}</div>
        </div>
        
        <div class="summary">
            <div class="stat-card">
                <div class="stat-label">Total Lectures</div>
                <div class="stat-number">{total_lectures}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Complete</div>
                <div class="stat-number complete">✓ {complete_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Encrypted</div>
                <div class="stat-number encrypted">🔒 {encrypted_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Incomplete</div>
                <div class="stat-number incomplete">⚠ {incomplete_count}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Missing</div>
                <div class="stat-number missing">✗ {missing_count}</div>
            </div>
        </div>
        
        <div class="success-rate">
            Success Rate: {success_rate:.1f}%
        </div>
"""
    
    # Add sections for each category
    sections = [
        ('complete', '✓ Complete Lectures', 'complete', verification_results['complete']),
        ('encrypted_pending', '🔒 Encrypted Lectures (Pending Decryption)', 'encrypted', verification_results['encrypted_pending']),
        ('incomplete', '⚠ Incomplete Lectures', 'incomplete', verification_results['incomplete']),
        ('missing', '✗ Missing Lectures', 'missing', verification_results['missing'])
    ]
    
    for section_id, section_title, css_class, items in sections:
        if items:
            html_content += f"""
        <div class="section">
            <h2>{section_title} ({len(items)})</h2>
            <ul class="lecture-list">
"""
            for item in items:
                file_info = f"<span><span class=\"label\">File:</span> {item['file']}</span>" if item.get('file') else ""
                size_info = f"<span><span class=\"label\">Size:</span> {_format_file_size(item['size'])}</span>" if item.get('size', 0) > 0 else ""
                reason_info = f"<span><span class=\"label\">Status:</span> {item['reason']}</span>" if item.get('reason') else ""
                chapter_info = f"<span><span class=\"label\">Chapter:</span> {item['chapter']}</span>" if item.get('chapter') else ""
                
                html_content += f"""
                <li class="lecture-item {css_class}">
                    <div class="lecture-title">
                        {item['title']}
                        <span class="badge {css_class}">{section_title.split()[0]}</span>
                    </div>
                    <div class="lecture-details">
                        {file_info}
                        {size_info}
                        {reason_info}
                        {chapter_info}
                    </div>
                </li>
"""
            
            html_content += """
            </ul>
        </div>
"""
        else:
            html_content += f"""
        <div class="section">
            <h2>{section_title} ({len(items)})</h2>
            <div class="empty-state">No {section_title.lower().split()[1]} found</div>
        </div>
"""
    
    html_content += f"""
        <div class="timestamp">
            Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    
    # Save HTML report
    report_path = os.path.join(course_dir, 'download_verification_report.html')
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML verification report saved to: {report_path}")
    except Exception as e:
        logger.error(f"Failed to save HTML verification report: {e}")
        return None
    
    return report_path


def generate_verification_report(course_dir: str, course_name: str, 
                                verification_results: Dict) -> str:
    """
    Generate both HTML and JSON verification reports
    
    Args:
        course_dir: Path to course directory
        course_name: Name of the course
        verification_results: Results from verify_course_downloads
        
    Returns:
        Path to the generated HTML report file (primary format)
    """
    # Generate HTML report (primary)
    html_report_path = generate_html_report(course_dir, course_name, verification_results)
    
    # Also generate JSON report for programmatic access
    total_lectures = len(verification_results['complete']) + \
                    len(verification_results['incomplete']) + \
                    len(verification_results['missing']) + \
                    len(verification_results['encrypted_pending'])
    
    complete_count = len(verification_results['complete'])
    success_rate = (complete_count / total_lectures * 100) if total_lectures > 0 else 0
    
    report_data = {
        'course_name': course_name,
        'verification_date': datetime.now().isoformat(),
        'total_lectures': total_lectures,
        'complete': verification_results['complete'],
        'incomplete': verification_results['incomplete'],
        'missing': verification_results['missing'],
        'encrypted_pending': verification_results['encrypted_pending'],
        'summary': {
            'success_rate': f"{success_rate:.1f}%",
            'total_complete': complete_count,
            'total_incomplete': len(verification_results['incomplete']),
            'total_missing': len(verification_results['missing']),
            'total_encrypted': len(verification_results['encrypted_pending'])
        }
    }
    
    json_report_path = os.path.join(course_dir, 'download_status.json')
    
    try:
        with open(json_report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON verification report saved to: {json_report_path}")
    except Exception as e:
        logger.error(f"Failed to save JSON verification report: {e}")
    
    return html_report_path  # Return HTML path as primary


def load_id_to_title_map(course_dir: str) -> Optional[Dict[str, str]]:
    """
    Load the id_to_title.json file from the course directory
    
    Args:
        course_dir: Path to the course directory
        
    Returns:
        Dict mapping lecture IDs to titles, or None if not found
    """
    map_path = os.path.join(course_dir, 'id_to_title.json')
    
    if not os.path.exists(map_path):
        logger.warning(f"id_to_title.json not found in {course_dir}")
        return None
    
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load id_to_title.json: {e}")
        return None


if __name__ == "__main__":
    # Simple test/demo mode
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python download_verifier.py <course_directory>")
        sys.exit(1)
    
    course_dir = sys.argv[1]
    
    # Load the manifest
    id_to_title_map = load_id_to_title_map(course_dir)
    
    if not id_to_title_map:
        print(f"Error: Could not load id_to_title.json from {course_dir}")
        sys.exit(1)
    
    print(f"\nVerifying downloads for course in: {course_dir}")
    print(f"Total lectures in manifest: {len(id_to_title_map)}\n")
    
    # Run verification
    results = verify_course_downloads(course_dir, id_to_title_map)
    
    # Generate report
    course_name = os.path.basename(course_dir)
    report_path = generate_verification_report(course_dir, course_name, results)
    
    # Print summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    print(f"Complete:          {len(results['complete'])}")
    print(f"Incomplete:        {len(results['incomplete'])}")
    print(f"Missing:           {len(results['missing'])}")
    print(f"Encrypted Pending: {len(results['encrypted_pending'])}")
    print("="*60)
    
    if report_path:
        print(f"\nDetailed report saved to: {report_path}")
