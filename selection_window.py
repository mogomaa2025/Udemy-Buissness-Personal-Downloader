import os
from pathvalidate import sanitize_filename

def show_video_selection_window(chapters, course_out_dir="", id_to_title_map=None):
    """
    Display a window with chapters and their videos, each video with a thumbnail and checkbox.
    Provide Select All and Uncheck All buttons.
    Returns a dict/list of selected videos (chapter/video ids).
    chapters: list of dicts, each with 'title', 'videos': [{'title', 'thumbnail_url', 'id', ...}]
    """
    import tkinter as tk
    from tkinter import ttk, messagebox
    
    id_to_title_map = {
        str(key): value
        for key, value in (id_to_title_map or {}).items()
        if key is not None
    }
    normalized_course_dir = os.path.abspath(course_out_dir) if course_out_dir else ""
    chapter_file_cache = {}

    def _collect_chapter_files(chapter_title, chapter_id):
        """Return a mapping of filename->size for the given chapter directory."""
        if not normalized_course_dir:
            return {}, None

        folder_name = None
        title_candidate = chapter_title if isinstance(chapter_title, str) and chapter_title else None
        if title_candidate:
            folder_name = sanitize_filename(title_candidate)
        if not folder_name:
            fallback = None
            if chapter_id is not None:
                fallback = f"chapter_{chapter_id}"
            elif title_candidate is None:
                fallback = "chapter"
            if fallback:
                folder_name = sanitize_filename(fallback)

        if not folder_name:
            return {}, None

        chapter_path = os.path.join(normalized_course_dir, folder_name)
        if chapter_path in chapter_file_cache:
            return chapter_file_cache[chapter_path], chapter_path

        files_map = {}
        if os.path.isdir(chapter_path):
            try:
                with os.scandir(chapter_path) as iterator:
                    for entry in iterator:
                        if entry.is_file():
                            try:
                                files_map[entry.name] = entry.stat().st_size
                            except OSError:
                                files_map[entry.name] = 0
            except OSError:
                files_map = {}

        chapter_file_cache[chapter_path] = files_map
        return files_map, chapter_path

    def _match_download(candidate_names, fallback_prefixes, chapter_files):
        if not chapter_files:
            return False
        for name in candidate_names:
            size = chapter_files.get(name)
            if size and size > 0:
                return True
        for prefix in fallback_prefixes:
            if not prefix:
                continue
            for filename, file_size in chapter_files.items():
                if file_size and (filename.startswith(prefix) or prefix in filename):
                    return True
        return False

    def _is_video_downloaded(video, chapter_files):
        vid_id = video.get("id")
        raw_vid_title = video.get("title")
        lecture_type = video.get("type", "video")
        asset_type = (video.get("asset_type") or "").lower()
        asset_filename = video.get("asset_filename")

        lecture_title_from_map = id_to_title_map.get(str(vid_id))

        sanitized_map_title = sanitize_filename(lecture_title_from_map) if isinstance(lecture_title_from_map, str) and lecture_title_from_map else None
        sanitized_video_title = sanitize_filename(raw_vid_title) if isinstance(raw_vid_title, str) and raw_vid_title else None

        base_identifiers = []
        for candidate in (sanitized_map_title, sanitized_video_title, str(vid_id) if vid_id is not None else None):
            if candidate and candidate not in base_identifiers:
                base_identifiers.append(candidate)

        candidate_names = set()

        if lecture_type == "quiz":
            for base in base_identifiers:
                candidate_names.add(f"{base}.html")
            fallback_prefixes = base_identifiers
        elif lecture_type == "file":
            if asset_filename:
                candidate_names.add(asset_filename)
                sanitized_asset = sanitize_filename(asset_filename)
                candidate_names.add(sanitized_asset)
                asset_suffix = os.path.splitext(asset_filename)[1]
                if asset_suffix:
                    for base in base_identifiers:
                        candidate_names.add(f"{base}{asset_suffix}")
            fallback_prefixes = base_identifiers

            if asset_type == "article":
                for base in base_identifiers:
                    candidate_names.add(f"{base}.html")
            elif asset_type in ("e-book", "ebook"):
                for base in base_identifiers:
                    candidate_names.add(f"{base}.pdf")
            elif asset_type == "presentation":
                for base in base_identifiers:
                    candidate_names.add(f"{base}.pptx")
            elif asset_type == "audio":
                for base in base_identifiers:
                    candidate_names.add(f"{base}.mp3")
            elif asset_type == "file":
                for base in base_identifiers:
                    candidate_names.add(f"{base}.zip")
            else:
                for base in base_identifiers:
                    candidate_names.add(f"{base}.pdf")
        else:
            fallback_prefixes = base_identifiers
            if not base_identifiers and vid_id is not None:
                fallback_prefixes = [str(vid_id)]
            for base in fallback_prefixes:
                candidate_names.add(f"{base}.mp4")
                candidate_names.add(f"{base}.mkv")
                candidate_names.add(f"{base}.webm")

        return _match_download(candidate_names, fallback_prefixes, chapter_files)

    # Modern style variables (same as main GUI)
    bg_main = "#4E342E"  # brown dark
    bg_frame = "#6D4C41"  # brown medium
    bg_entry = "#A1887F"  # brown light
    fg_text = "#FFF8E1"  # cream
    fg_label = "#FFCCBC"  # light orange
    accent = "#D84315"    # deep orange accent
    accent2 = "#8D6E63"   # muted brown
    font_title = ("Segoe UI", 18, "bold")
    font_chapter = ("Segoe UI", 13, "bold")
    font_video = ("Segoe UI", 11)

    # Prevent extra Tk window: create hidden root if needed
    if not hasattr(tk, '_default_root') or tk._default_root is None:
        hidden_root = tk.Tk()
        hidden_root.withdraw()
    root = tk.Toplevel()
    root.title("Select Lectures to Download")
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    except Exception:
        sw, sh = 1024, 768
    sel_w = max(540, min(900, sw - 120))
    sel_h = max(420, min(600, sh - 160))
    root.geometry(f"{sel_w}x{sel_h}")
    root.minsize(480, 360)
    root.resizable(True, True)
    root.configure(bg=bg_main)
    root.grab_set()

    # Ensure the window appears in front and focused
    try:
        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.focus_force()
        root.attributes("-topmost", True)
        # Drop topmost after a short delay so it behaves like a normal window
        root.after(800, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

    title = tk.Label(root, text="Select Lectures to Download", font=font_title, bg=bg_main, fg=accent)
    title.pack(pady=(24, 8))
    
    # Add legend for icons and colors
    legend_frame = tk.Frame(root, bg=bg_main)
    legend_frame.pack(pady=(0, 8))
    
    legend_text = "Legend: 🎥 Videos | 📝 Quizzes | 📎 Videos with Assets | 📄 Articles | 📚 E-books | 📊 Presentations | 🎵 Audio | 📁 Files"
    legend_label = tk.Label(legend_frame, text=legend_text, font=("Segoe UI", 9), bg=bg_main, fg=fg_label)
    legend_label.pack()

    # Scrollable area
    main_frame = tk.Frame(root, bg=bg_main)
    main_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))
    canvas = tk.Canvas(main_frame, borderwidth=0, background=bg_frame, highlightthickness=0)
    frame = tk.Frame(canvas, background=bg_frame)
    vsb = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    hsb = tk.Scrollbar(main_frame, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    hsb.pack(side="bottom", fill="x")
    canvas.create_window((0,0), window=frame, anchor="nw")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    frame.bind("<Configure>", on_frame_configure)

    # Enable mouse wheel scrolling
    def _on_mousewheel(event):
        # For Windows, event.delta is multiples of 120
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    check_vars = {}
    chapter_frames = []

    for chap_idx, chapter in enumerate(chapters):
        chap_id = chapter.get('id')
        raw_chap_title = chapter.get('title')
        if isinstance(raw_chap_title, str) and raw_chap_title.strip():
            chap_title = raw_chap_title
        elif chap_id is not None:
            chap_title = f"Chapter {chap_id}"
        else:
            chap_title = f"Chapter {chap_idx + 1}"

        chapter_files, _chapter_path = _collect_chapter_files(chap_title, chap_id)
        chap_frame = tk.LabelFrame(frame, text=chap_title, padx=8, pady=4, bg=bg_entry, fg=accent, font=font_chapter, bd=2, relief="groove", labelanchor="nw")
        chap_frame.pack(fill="x", padx=8, pady=6, anchor="n")
        chapter_frames.append(chap_frame)

        # Per-chapter controls (Select All / None)
        chap_ctrl_row = tk.Frame(chap_frame, bg=bg_entry)
        chap_ctrl_row.pack(fill="x", pady=(0, 4))
        chap_vid_vars = []
        def _chap_select_all(vars_ref=chap_vid_vars):
            for _v in vars_ref:
                _v.set(True)
            validate_selection()
        def _chap_unselect_all(vars_ref=chap_vid_vars):
            for _v in vars_ref:
                _v.set(False)
            validate_selection()
        tk.Button(chap_ctrl_row, text="Select chapter", command=_chap_select_all, width=14).pack(side="left")
        tk.Button(chap_ctrl_row, text="Uncheck chapter", command=_chap_unselect_all, width=14).pack(side="left", padx=(6, 0))

        for video in chapter.get('videos', []):
            vid_id = video.get('id')
            vid_title = video.get('title')
            var = tk.BooleanVar(value=True)
            check_vars[vid_id] = var
            chap_vid_vars.append(var)
            row = tk.Frame(chap_frame, bg=bg_entry)
            row.pack(fill="x", pady=2, anchor="w")

            # Determine if video/quiz/file is already downloaded
            is_downloaded = _is_video_downloaded(video, chapter_files)
            
            cb = tk.Checkbutton(row, variable=var, bg=bg_entry, fg=fg_label, activebackground=bg_entry, activeforeground=accent, selectcolor=bg_main, font=font_video)
            cb.pack(side="left")
            
            # Determine lecture type and set appropriate color
            lecture_type = video.get("type", "video")
            has_assets = video.get("has_assets", False)
            asset_type = video.get("asset_type", "")
            
            if lecture_type == "quiz":
                type_indicator = "📝 "
                type_color = "#FF9800"  # Orange for quizzes
            elif lecture_type == "file":
                # Different icons for different file types
                if asset_type == "article":
                    type_indicator = "📄 "
                    type_color = "#2196F3"  # Blue for articles
                elif asset_type in ["e-book", "ebook"]:
                    type_indicator = "📚 "
                    type_color = "#795548"  # Brown for e-books
                elif asset_type == "presentation":
                    type_indicator = "📊 "
                    type_color = "#607D8B"  # Blue-grey for presentations
                elif asset_type == "audio":
                    type_indicator = "🎵 "
                    type_color = "#E91E63"  # Pink for audio
                else:  # generic file
                    type_indicator = "📁 "
                    type_color = "#9E9E9E"  # Grey for generic files
            else:  # video
                type_indicator = "🎥 "
                if has_assets:
                    type_indicator = "📎 "  # Paperclip icon for videos with assets
                    type_color = "#9C27B0"  # Purple for videos with assets
                else:
                    type_color = "#4CAF50" if is_downloaded else "#F44336"  # Green/Red for videos without assets
            
            # Change label color based on download status and type
            label_color = type_color
            display_title = f"{type_indicator}{vid_title}"
            lbl_title = tk.Label(row, text=display_title, anchor="w", bg=bg_entry, fg=label_color, font=font_video)
            lbl_title.pack(side="left", padx=8, fill="x", expand=True)

    # Select All / Uncheck All buttons
    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="x", pady=8)
    def select_all():
        for v in check_vars.values():
            v.set(True)
        validate_selection()
    def uncheck_all():
        for v in check_vars.values():
            v.set(False)
        validate_selection()
    btn_sel = tk.Button(btn_frame, text="Select All", command=select_all, width=12)
    btn_unsel = tk.Button(btn_frame, text="Uncheck All", command=uncheck_all, width=12)
    btn_sel.pack(side="left", padx=10)
    btn_unsel.pack(side="left", padx=10)

    # OK/Cancel
    result = []
    def on_ok():
        result.clear()
        for chap in chapters:
            for video in chap.get('videos', []):
                vid_id = video.get('id')
                if check_vars[vid_id].get():
                    result.append((chap.get('id', chap.get('title')), vid_id))
        root.grab_release()
        root.destroy()
    def on_cancel():
        result.clear()
        root.grab_release()
        root.destroy()
    btn_ok = tk.Button(btn_frame, text="OK", command=on_ok, width=12, state="normal")
    btn_cancel = tk.Button(btn_frame, text="Cancel", command=on_cancel, width=12)
    btn_ok.pack(side="right", padx=10)
    btn_cancel.pack(side="right", padx=10)

    def validate_selection(*args):
        any_selected = any(v.get() for v in check_vars.values())
        btn_ok.config(state="normal" if any_selected else "disabled")
    for v in check_vars.values():
        v.trace_add('write', validate_selection)
    validate_selection()

    root.wait_window()
    return result
