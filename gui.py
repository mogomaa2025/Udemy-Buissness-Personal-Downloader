def show_video_selection_window(chapters, course_out_dir="", id_to_title_map={}):
    """
    Display a window with chapters and their videos, each video with a thumbnail and checkbox.
    Provide Select All and Uncheck All buttons.
    Returns a dict/list of selected videos (chapter/video ids).
    chapters: list of dicts, each with 'title', 'videos': [{'title', 'thumbnail_url', 'id', ...}]
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

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
    root.title("Select Videos to Download")
    root.geometry("900x600")
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

    title = tk.Label(root, text="Select Videos to Download", font=font_title, bg=bg_main, fg=accent)
    title.pack(pady=(24, 8))

    # Scrollable area
    main_frame = tk.Frame(root, bg=bg_main)
    main_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))
    canvas = tk.Canvas(main_frame, borderwidth=0, background=bg_frame, highlightthickness=0)
    frame = tk.Frame(canvas, background=bg_frame)
    vsb = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
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
        chap_id = chapter.get('id', chapter.get('title'))
        chap_title = chapter.get('title', str(chap_id))
        chap_frame = tk.LabelFrame(frame, text=chap_title, padx=8, pady=4, bg=bg_entry, fg=accent, font=font_chapter, bd=2, relief="groove", labelanchor="nw")
        chap_frame.pack(fill="x", padx=8, pady=6, anchor="n")
        chapter_frames.append(chap_frame)
        for video in chapter.get('videos', []):
            vid_id = video.get('id')
            vid_title = video.get('title')
            var = tk.BooleanVar(value=True)
            check_vars[vid_id] = var
            row = tk.Frame(chap_frame, bg=bg_entry)
            row.pack(fill="x", pady=2, anchor="w")

            # Determine if video is downloaded
            is_downloaded = False
            if course_out_dir and id_to_title_map:
                chapter_directory_name = sanitize_filename(chapter.get('title', ''))
                
                lecture_title_from_map = id_to_title_map.get(str(vid_id))
                
                if lecture_title_from_map:
                    sanitized_video_filename = sanitize_filename(lecture_title_from_map) + ".mp4"
                    video_filepath = os.path.join(course_out_dir, chapter_directory_name, sanitized_video_filename)
                    if os.path.exists(video_filepath) and os.path.getsize(video_filepath) > 0:
                        is_downloaded = True
            
            cb = tk.Checkbutton(row, variable=var, bg=bg_entry, fg=fg_label, activebackground=bg_entry, activeforeground=accent, selectcolor=bg_main, font=font_video)
            cb.pack(side="left")
            
            # Change label color based on download status
            label_color = "green" if is_downloaded else "red"
            lbl_title = tk.Label(row, text=vid_title, anchor="w", bg=bg_entry, fg=label_color, font=font_video)
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

import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import json
import re
import shutil
from pathvalidate import sanitize_filename
import os


class UdemyDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Udemy Course Downloader & Combiner - CopyRight : Eng. Mohamed Gomaa")
        self.config_path = "config.json"
        self.ffmpeg_processes = []
        self.create_widgets()
        self.ffmpeg_path = "ffmpeg"  # Assume ffmpeg is in PATH
        self.load_config()

    def create_widgets(self):
        # Modern glass-like style
        # Brown Material Skin Colors
        bg_main = "#4E342E"  # brown dark
        bg_frame = "#6D4C41"  # brown medium
        bg_entry = "#A1887F"  # brown light
        fg_text = "#FFF8E1"  # cream
        fg_label = "#FFCCBC"  # light orange
        accent = "#D84315"    # deep orange accent
        accent2 = "#8D6E63"   # muted brown

        self.root.configure(bg=bg_main)
        self.root.grid_rowconfigure(100, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        label_style = {"bg": bg_main, "fg": fg_label, "font": ("Segoe UI", 11, "bold")}
        entry_style = {"bg": bg_entry, "fg": bg_main, "insertbackground": fg_text, "highlightbackground": accent2, "font": ("Segoe UI", 11)}
        button_style = {"bg": accent2, "fg": fg_label, "activebackground": accent, "activeforeground": fg_text, "font": ("Segoe UI", 11, "bold")}
        check_style = {"bg": bg_main, "fg": fg_label, "activebackground": bg_main, "activeforeground": fg_label, "selectcolor": bg_entry, "font": ("Segoe UI", 11)}

        # Add extra top padding to window and title
        self.root.geometry("1000x800+100+60")  # Larger default size
        self.root.minsize(900, 700)
        self.root.resizable(True, True)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
        for i in range(8):
            self.root.grid_rowconfigure(i, weight=0)
        self.root.grid_rowconfigure(100, weight=1)
        title = tk.Label(self.root, text="Udemy Course Downloader", font=("Segoe UI", 20, "bold"), bg=bg_main, fg=accent)
        title.grid(row=0, column=0, columnspan=4, pady=(40, 20), padx=40, sticky="nsew")

        # Add a canvas and scrollbar for main content
        canvas_frame = tk.Frame(self.root, bg=bg_main)
        canvas_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(canvas_frame, bg=bg_frame, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        # Make the canvas expandable
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # Frame inside canvas
        main_frame = tk.Frame(canvas, bg=bg_frame)
        main_frame_id = canvas.create_window((0,0), window=main_frame, anchor="nw")
        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        main_frame.bind("<Configure>", on_configure)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        for i in range(4):
            main_frame.grid_columnconfigure(i, weight=1)
        for i in range(12):
            main_frame.grid_rowconfigure(i, weight=0)

        row = 0
        def add_tooltip(widget, text):
            def on_enter(e):
                widget.tooltip = tk.Toplevel(widget)
                widget.tooltip.wm_overrideredirect(True)
                x = widget.winfo_rootx() + 20
                y = widget.winfo_rooty() + 20
                widget.tooltip.wm_geometry(f"+{x}+{y}")
                label = tk.Label(widget.tooltip, text=text, bg=bg_frame, fg=accent, font=("Segoe UI", 9), relief="solid", borderwidth=1)
                label.pack()
            def on_leave(e):
                if hasattr(widget, 'tooltip'):
                    widget.tooltip.destroy()
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        # Course URL
        lbl_course = tk.Label(main_frame, text="Course URL:", **label_style)
        lbl_course.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.course_url_entry = tk.Entry(main_frame, width=60, **entry_style)
        self.course_url_entry.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_course, "Paste the Udemy course URL here.")
        row += 1

        # Access Token
        lbl_token = tk.Label(main_frame, text="Access Token:", **label_style)
        lbl_token.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.token_entry = tk.Entry(main_frame, width=60, **entry_style)
        self.token_entry.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_token, "Paste your Udemy access token here.")
        row += 1

        # Udemy Type Selection
        lbl_udemy_type = tk.Label(main_frame, text="Udemy Type:", **label_style)
        lbl_udemy_type.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.udemy_type_var = tk.StringVar(value="normal")
        udemy_type_frame = tk.Frame(main_frame, bg=bg_frame)
        udemy_type_frame.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        tk.Radiobutton(udemy_type_frame, text="Normal Udemy (www.udemy.com)", variable=self.udemy_type_var, value="normal", **check_style).pack(side="left", padx=(0, 20))
        tk.Radiobutton(udemy_type_frame, text="Udemy Business (enterprise)", variable=self.udemy_type_var, value="business", **check_style).pack(side="left")
        add_tooltip(lbl_udemy_type, "Choose between normal Udemy or Udemy Business/Enterprise portal.")
        row += 1

        # Chapter
        lbl_chapter = tk.Label(main_frame, text="Chapter (e.g. 1,3-5):", **label_style)
      
        self.chapter_entry = tk.Entry(main_frame, width=20, **entry_style)
 
        add_tooltip(lbl_chapter, "Specify chapters to download.")
        row += 1

        # Lecture/Video Number
        lbl_lecture = tk.Label(main_frame, text="Video (e.g. 1,3-5):", **label_style)
       
        self.lecture_entry = tk.Entry(main_frame, width=20, **entry_style)
   
        add_tooltip(lbl_lecture, "Specify specific lectures/videos to download within the selected chapters.")
        row += 1

        # Quality
        lbl_quality = tk.Label(main_frame, text="Quality (e.g. 720):", **label_style)
        lbl_quality.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.quality_entry = tk.Entry(main_frame, width=10, **entry_style)
        self.quality_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_quality, "Video quality (e.g. 720, 1080)")
        row += 1

        # Language Dropdown
        lbl_lang = tk.Label(main_frame, text="Caption Language:", **label_style)
        lbl_lang.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.lang_var = tk.StringVar(value="en")
        self.lang_dropdown = tk.OptionMenu(main_frame, self.lang_var, "en", "ar")
        self.lang_dropdown.config(
            width=10,
            bg=bg_entry,
            fg=bg_main,
            font=("Segoe UI", 11),
            highlightbackground=accent2,
            activebackground=accent2,
            activeforeground=fg_label
        )
        # For OptionMenu, also set menu colors
        menu = self.lang_dropdown['menu']
        menu.config(bg=bg_entry, fg=bg_main, font=("Segoe UI", 11))
        self.lang_dropdown.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_lang, "Select caption language.")
        row += 1

        # Concurrent Downloads
        lbl_concurrent = tk.Label(main_frame, text="Concurrent Downloads:", **label_style)
        lbl_concurrent.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.concurrent_entry = tk.Entry(main_frame, width=10, **entry_style)
        self.concurrent_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_concurrent, "Number of downloads to run in parallel.")
        row += 1

        # Output Directory
        lbl_out = tk.Label(main_frame, text="Output Directory:", **label_style)
        lbl_out.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.out_entry = tk.Entry(main_frame, width=40, **entry_style)
        self.out_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        btn_browse = tk.Button(main_frame, text="Browse", command=self.browse_out, **button_style)
        btn_browse.grid(row=row, column=2, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_out, "Choose where downloads will be saved.")
        row += 1

        # Log Level
        lbl_loglevel = tk.Label(main_frame, text="Log Level:", **label_style)
        lbl_loglevel.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.loglevel_entry = tk.Entry(main_frame, width=10, **entry_style)
        self.loglevel_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_loglevel, "Set log verbosity (e.g. info, debug)")
        row += 1

        # Browser
        lbl_browser = tk.Label(main_frame, text="Browser (for cookies):", **label_style)
        lbl_browser.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.browser_entry = tk.Entry(main_frame, width=15, **entry_style)
        self.browser_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_browser, "Browser used for cookies export.")
        row += 1

        # Separator
        sep1 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep1.grid(row=2, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Flags Frame
        flags_frame = tk.LabelFrame(self.root, text="Options", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        flags_frame.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(4):
            flags_frame.grid_columnconfigure(i, weight=1)
        for i in range(4):
            flags_frame.grid_rowconfigure(i, weight=0)

        self.use_h265 = tk.BooleanVar()
        self.use_nvenc = tk.BooleanVar()
        self.download_captions = tk.BooleanVar()
        self.download_assets = tk.BooleanVar()
        self.download_quizzes = tk.BooleanVar()
        self.keep_vtt = tk.BooleanVar()
        self.skip_lectures = tk.BooleanVar()
        self.skip_hls = tk.BooleanVar()
        self.info = tk.BooleanVar()
        self.id_as_course_name = tk.BooleanVar()
        self.subscription_course = tk.BooleanVar()
        self.save_to_file = tk.BooleanVar()
        self.load_from_file = tk.BooleanVar()
        self.continue_lecture_numbers = tk.BooleanVar()

        flag_row = 0
        tk.Checkbutton(flags_frame, text="Use H265", variable=self.use_h265, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Use NVENC", variable=self.use_nvenc, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Download Captions", variable=self.download_captions, **check_style).grid(row=flag_row, column=2, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Download Assets", variable=self.download_assets, **check_style).grid(row=flag_row, column=3, sticky="w", padx=4, pady=2)
        flag_row += 1
        tk.Checkbutton(flags_frame, text="Download Quizzes", variable=self.download_quizzes, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Keep VTT", variable=self.keep_vtt, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Skip Lectures", variable=self.skip_lectures, **check_style).grid(row=flag_row, column=2, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Skip HLS", variable=self.skip_hls, **check_style).grid(row=flag_row, column=3, sticky="w", padx=4, pady=2)
        flag_row += 1
        tk.Checkbutton(flags_frame, text="Info Only", variable=self.info, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="ID as Course Name", variable=self.id_as_course_name, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Subscription Course", variable=self.subscription_course, **check_style).grid(row=flag_row, column=2, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Save to File", variable=self.save_to_file, **check_style).grid(row=flag_row, column=3, sticky="w", padx=4, pady=2)
        flag_row += 1
        tk.Checkbutton(flags_frame, text="Load from File", variable=self.load_from_file, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Continue Lecture Numbers", variable=self.continue_lecture_numbers, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)

        # Separator
        sep2 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep2.grid(row=4, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Advanced Frame
        adv_frame = tk.LabelFrame(self.root, text="Advanced", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        adv_frame.grid(row=5, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(4):
            adv_frame.grid_columnconfigure(i, weight=1)
        for i in range(2):
            adv_frame.grid_rowconfigure(i, weight=0)

        adv_row = 0
        tk.Label(adv_frame, text="H265 CRF:", **label_style).grid(row=adv_row, column=0, sticky="e", pady=4, padx=4)
        self.h265_crf_entry = tk.Entry(adv_frame, width=10, **entry_style)
        self.h265_crf_entry.grid(row=adv_row, column=1, sticky="nsew", pady=4, padx=4)
        tk.Label(adv_frame, text="H265 Preset:", **label_style).grid(row=adv_row, column=2, sticky="e", pady=4, padx=4)
        self.h265_preset_entry = tk.Entry(adv_frame, width=10, **entry_style)
        self.h265_preset_entry.grid(row=adv_row, column=3, sticky="nsew", pady=4, padx=4)
        adv_row += 1

        tk.Label(adv_frame, text="Decryption Key:", **label_style).grid(row=adv_row, column=0, sticky="e", pady=4, padx=4)
        self.decryption_key_entry = tk.Entry(adv_frame, width=60, **entry_style)
        self.decryption_key_entry.grid(row=adv_row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)

        # Separator
        sep3 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep3.grid(row=6, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Buttons Frame
        btn_frame = tk.Frame(self.root, bg=bg_main)
        btn_frame.grid(row=7, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(3):
            btn_frame.grid_columnconfigure(i, weight=1)
        btn_frame.grid_rowconfigure(0, weight=1)

        tk.Button(btn_frame, text="Start Full Process", command=self.start_full_process, bg=accent, fg=fg_text, font=("Segoe UI", 12, "bold"), relief="flat").grid(row=0, column=0, pady=10, padx=10, sticky="nsew")
        tk.Button(btn_frame, text="Save Config", command=self.save_config, bg=accent2, fg=fg_label, font=("Segoe UI", 12, "bold"), relief="flat").grid(row=0, column=1, pady=10, padx=10, sticky="nsew")
        tk.Button(btn_frame, text="Stop & Clean", command=self.stop_and_clean, bg="#B71C1C", fg=fg_text, font=("Segoe UI", 12, "bold"), relief="flat").grid(row=0, column=2, pady=10, padx=10, sticky="nsew")

        # Status Frame
        status_frame = tk.LabelFrame(self.root, text="Status Log", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        status_frame.grid(row=100, column=0, columnspan=4, sticky="nsew", padx=40, pady=20)
        status_frame.grid_rowconfigure(0, weight=1)
        status_frame.grid_columnconfigure(0, weight=1)
        self.status_text = tk.Text(status_frame, height=10, width=80, state="disabled", bg=bg_entry, fg=bg_main, font=("Consolas", 11), relief="flat")
        self.status_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def stop_and_clean(self):
        # Signal stop if running
        if hasattr(self, 'stop_event') and self.stop_event:
            self.stop_event.set()
        # Terminate all running ffmpeg processes
        for proc in getattr(self, 'ffmpeg_processes', []):
            try:
                if proc.poll() is None:
                    proc.terminate()
                    self.log("Terminated ffmpeg process.")
            except Exception as e:
                self.log(f"Error terminating ffmpeg: {e}")
        self.ffmpeg_processes = []
        # Remove all files in ./logs/* and ./temp/*
        for folder in ["logs", "temp"]:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path):
                for f in os.listdir(folder_path):
                    try:
                        fp = os.path.join(folder_path, f)
                        if os.path.isfile(fp):
                            os.remove(fp)
                        elif os.path.isdir(fp):
                            import shutil
                            shutil.rmtree(fp)
                    except Exception as e:
                        self.log(f"Error removing {fp}: {e}")
        self.log("Stopped and cleaned logs/temp.")

    def browse_out(self):
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.out_entry.delete(0, tk.END)
            self.out_entry.insert(0, path)

    def browse_cookies(self):
        path = filedialog.askopenfilename(title="Select cookies.txt", filetypes=[("Text Files", "*.txt")])
        if path:
            self.cookies_path.set(path)

    def log(self, msg):
        self.status_text.config(state="normal")
        self.status_text.insert(tk.END, msg + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state="disabled")
        self.root.update()

    def stop_only(self):
        # Signal stop if running
        if hasattr(self, 'stop_event') and self.stop_event:
            self.stop_event.set()
        # Terminate all running ffmpeg processes
        for proc in getattr(self, 'ffmpeg_processes', []):
            try:
                if proc.poll() is None:
                    proc.terminate()
                    self.log("Terminated ffmpeg process.")
            except Exception as e:
                self.log(f"Error terminating ffmpeg: {e}")
        self.ffmpeg_processes = []
        self.log("Stopped process.")

    def close_progress_window(self):
        if hasattr(self, 'progress_win') and self.progress_win:
            self.progress_win.destroy()

    def start_full_process(self):
        import threading
        if hasattr(self, 'process_thread') and self.process_thread and self.process_thread.is_alive():
            self.log("A process is already running. Please wait or stop it first.")
            return
        # Create progress window
        self.progress_win = tk.Toplevel(self.root)
        self.progress_win.title("Progress Log")
        self.progress_win.geometry("700x400+200+120")
        self.progress_win.configure(bg="#6D4C41")
        self.progress_win.protocol("WM_DELETE_WINDOW", self.close_progress_window)
        # Status log in progress window
        self.status_text = tk.Text(self.progress_win, height=15, width=80, state="disabled", bg="#A1887F", fg="#4E342E", font=("Consolas", 11), relief="flat")
        self.status_text.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        # Progress bar
        s = ttk.Style()
        s.theme_use('clam') # 'clam', 'alt', 'default', 'classic'
        s.configure("TProgressbar", thickness=25, troughcolor="#6D4C41", background="#D84315", darkcolor="#D84315", lightcolor="#D84315", bordercolor="#6D4C41")
        self.progress_bar = ttk.Progressbar(self.progress_win, orient="horizontal", length=500, mode="determinate", style="TProgressbar")
        self.progress_bar.pack(pady=(0, 5), padx=16, fill="x")

        # Progress label
        self.progress_label = tk.Label(self.progress_win, text="Initializing...", bg="#6D4C41", fg="#FFCCBC", font=("Segoe UI", 11, "bold"))
        self.progress_label.pack(pady=(0, 10))
        
        # Stop button in progress window
        stop_btn = tk.Button(self.progress_win, text="Stop", command=self.stop_only, bg="#B71C1C", fg="#FFF8E1", font=("Segoe UI", 12, "bold"), relief="flat")
        stop_btn.pack(pady=(0, 16))
        self.stop_event = threading.Event()
        self.process_thread = threading.Thread(target=self._run_full_process, daemon=True)
        self.process_thread.start()

        # Initialize progress variables
        self.total_lectures = 0
        self.completed_lectures = 0

    def _run_full_process(self):
        self.save_config()
        course_url = self.course_url_entry.get().strip()
        token = self.token_entry.get().strip()
        chapter = self.chapter_entry.get().strip()
        lecture = self.lecture_entry.get().strip()
        quality = self.quality_entry.get().strip()
        lang = self.lang_var.get().strip()
        concurrent = self.concurrent_entry.get().strip()
        out_dir = self.out_entry.get().strip()
        loglevel = self.loglevel_entry.get().strip()
        browser = self.browser_entry.get().strip()
        h265_crf = self.h265_crf_entry.get().strip()
        h265_preset = self.h265_preset_entry.get().strip()
        import threading, queue
        self.save_config()
        course_url = self.course_url_entry.get().strip()
        token = self.token_entry.get().strip()
        chapter = self.chapter_entry.get().strip()
        quality = self.quality_entry.get().strip()
        lang = self.lang_var.get().strip()
        concurrent = self.concurrent_entry.get().strip()
        out_dir = self.out_entry.get().strip()
        loglevel = self.loglevel_entry.get().strip()
        browser = self.browser_entry.get().strip()
        h265_crf = self.h265_crf_entry.get().strip()
        h265_preset = self.h265_preset_entry.get().strip()
        decryption_key = self.decryption_key_entry.get().strip()

        if not course_url or not token:
            self.log("Course URL and Access Token are required.")
            messagebox.showerror("Input Error", "Course URL and Access Token are required.")
            return
        if not decryption_key:
            self.log("Decryption key is required.")
            messagebox.showerror("Input Error", "Decryption key is required.")
            return

        # Parse chapters
        chapters = []
        if chapter:
            for part in chapter.split(','):
                if '-' in part:
                    try:
                        start, end = part.split('-')
                        start = int(start.strip())
                        end = int(end.strip())
                        chapters.extend(list(range(start, end+1)))
                    except Exception:
                        continue
                else:
                    try:
                        chapters.append(int(part.strip()))
                    except Exception:
                        continue
        else:
            chapters = [None]  # Download all if not specified

        search_base = out_dir if out_dir else os.path.join(os.getcwd(), "out_dir")

        for chap in chapters:
            if self.stop_event.is_set():
                self.log("Stopped before chapter download.")
                return
            self.log(f"Starting download for chapter: {chap if chap else 'ALL'}...")
            download_cmd = [sys.executable, "main.py", "--course-url", course_url, "--bearer", token]
            if chap:
                download_cmd += ["--chapter", str(chap)]
            if lecture:
                download_cmd += ["--lecture", lecture]
            if quality:
                download_cmd += ["--quality", quality]
            # Only add --download-captions and -l <lang> if Download Captions is checked
            if self.download_captions.get():
                download_cmd.append("--download-captions")
                if lang:
                    download_cmd += ["-l", lang]
            if concurrent:
                download_cmd += ["--concurrent-downloads", concurrent]
            if out_dir:
                download_cmd += ["--out", out_dir]
            if loglevel:
                download_cmd += ["--log-level", loglevel]
            if browser:
                download_cmd += ["--browser", browser]
            if self.use_h265.get():
                download_cmd.append("--use-h265")
            if self.use_nvenc.get():
                download_cmd.append("--use-nvenc")
            if self.download_captions.get():
                download_cmd.append("--download-captions")
            if self.download_assets.get():
                download_cmd.append("--download-assets")
            if self.download_quizzes.get():
                download_cmd.append("--download-quizzes")
            if self.keep_vtt.get():
                download_cmd.append("--keep-vtt")
            if self.skip_lectures.get():
                download_cmd.append("--skip-lectures")
            if self.skip_hls.get():
                download_cmd.append("--skip-hls")
            if self.info.get():
                download_cmd.append("--info")
            if self.id_as_course_name.get():
                download_cmd.append("--id-as-course-name")
            if self.subscription_course.get():
                download_cmd.append("--subscription-course")
            if self.save_to_file.get():
                download_cmd.append("--save-to-file")
            if self.load_from_file.get():
                download_cmd.append("--load-from-file")
            if self.continue_lecture_numbers.get():
                download_cmd.append("--continue-lecture-numbers")
            if h265_crf:
                download_cmd += ["--h265-crf", h265_crf]
            if h265_preset:
                download_cmd += ["--h265-preset", h265_preset]

            self.log(f"Running: {' '.join(download_cmd)}")
            try:
                proc = subprocess.Popen(download_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                def enqueue_output(pipe, q, label):
                    for line in iter(pipe.readline, ''):
                        q.put((label, line))
                    pipe.close()

                q = queue.Queue()
                t_out = threading.Thread(target=enqueue_output, args=(proc.stdout, q, 'STDOUT'))
                t_err = threading.Thread(target=enqueue_output, args=(proc.stderr, q, 'STDERR'))
                t_out.start()
                t_err.start()

                while True:
                    if self.stop_event.is_set():
                        proc.terminate()
                        self.log("Process terminated by user.")
                        break
                    try:
                        label, line = q.get(timeout=0.1)
                        if line:
                            self.log(line.strip())
                    except queue.Empty:
                        if proc.poll() is not None:
                            break
                t_out.join()
                t_err.join()
                if proc.returncode != 0:
                    self.log(f"Process exited with errors for chapter {chap}.")
                    messagebox.showerror("Download Error", f"Download failed for chapter {chap}. See log.")
                    return
            except Exception as e:
                self.log(f"Error running download for chapter {chap}: {e}")
                return

            # Step 2: Decrypt
            if self.stop_event.is_set():
                self.log("Stopped before decryption.")
                return
            self.log(f"Starting decryption for chapter {chap if chap else 'ALL'}...")
            self.decrypt_files(decryption_key, search_base)

            # Step 3: Combine
            if self.stop_event.is_set():
                self.log("Stopped before combining.")
                return
            self.log(f"Combining audio and video for chapter {chap if chap else 'ALL'}...")
            self.combine_files(search_base)

            # Step 4: Clean up temp folders
            if self.stop_event.is_set():
                self.log("Stopped before final cleanup.")
                return
            self.log(f"Cleaning up temporary directories for chapter {chap if chap else 'ALL'}...")
            self.cleanup_temp_folders(search_base)

        self.log("All chapters processed.")
        self.cleanup_temp_folders(search_base)
        
        self.log("All steps completed.")
    def save_config(self):
        # Save all current options to config.json
        config = {
            "course_url": self.course_url_entry.get().strip(),
            "token": self.token_entry.get().strip(),
            "udemy_type": self.udemy_type_var.get(),
            "chapter": self.chapter_entry.get().strip(),
            "lecture": self.lecture_entry.get().strip(),
            "quality": self.quality_entry.get().strip(),
            "lang": self.lang_var.get().strip(),
            "concurrent": self.concurrent_entry.get().strip(),
            "out_dir": self.out_entry.get().strip(),
            "loglevel": self.loglevel_entry.get().strip(),
            "browser": self.browser_entry.get().strip(),
            "h265_crf": self.h265_crf_entry.get().strip(),
            "h265_preset": self.h265_preset_entry.get().strip(),
            "decryption_key": self.decryption_key_entry.get().strip(),
            "use_h265": self.use_h265.get(),
            "use_nvenc": self.use_nvenc.get(),
            "download_captions": self.download_captions.get(),
            "download_assets": self.download_assets.get(),
            "download_quizzes": self.download_quizzes.get(),
            "keep_vtt": self.keep_vtt.get(),
            "skip_lectures": self.skip_lectures.get(),
            "skip_hls": self.skip_hls.get(),
            "info": self.info.get(),
            "id_as_course_name": self.id_as_course_name.get(),
            "subscription_course": self.subscription_course.get(),
            "save_to_file": self.save_to_file.get(),
            "load_from_file": self.load_from_file.get(),
            "continue_lecture_numbers": self.continue_lecture_numbers.get(),
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log(f"Error saving config: {e}")

    def load_config(self):
        # Load last options from config.json
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            self.course_url_entry.insert(0, config.get("course_url", ""))
            self.token_entry.insert(0, config.get("token", ""))
            self.udemy_type_var.set(config.get("udemy_type", "normal"))
            self.chapter_entry.insert(0, config.get("chapter", ""))
            self.lecture_entry.insert(0, config.get("lecture", ""))
            self.quality_entry.insert(0, config.get("quality", ""))
            self.lang_var.set(config.get("lang", "en"))
            self.concurrent_entry.insert(0, config.get("concurrent", ""))
            self.out_entry.insert(0, config.get("out_dir", ""))
            self.loglevel_entry.insert(0, config.get("loglevel", ""))
            self.browser_entry.insert(0, config.get("browser", ""))
            self.h265_crf_entry.insert(0, config.get("h265_crf", ""))
            self.h265_preset_entry.insert(0, config.get("h265_preset", ""))
            self.decryption_key_entry.insert(0, config.get("decryption_key", ""))
            self.use_h265.set(config.get("use_h265", False))
            self.use_nvenc.set(config.get("use_nvenc", False))
            self.download_captions.set(config.get("download_captions", False))
            self.download_assets.set(config.get("download_assets", False))
            self.download_quizzes.set(config.get("download_quizzes", False))
            self.keep_vtt.set(config.get("keep_vtt", False))
            self.skip_lectures.set(config.get("skip_lectures", False))
            self.skip_hls.set(config.get("skip_hls", False))
            self.info.set(config.get("info", False))
            self.id_as_course_name.set(config.get("id_as_course_name", False))
            self.subscription_course.set(config.get("subscription_course", False))
            self.save_to_file.set(config.get("save_to_file", False))
            self.load_from_file.set(config.get("load_from_file", False))
            self.continue_lecture_numbers.set(config.get("continue_lecture_numbers", False))
        except Exception as e:
            self.log(f"Error loading config: {e}")
        # Do NOT auto-run process on config load

    def decrypt_files(self, decryption_key, search_dir):
        # Find all encrypted files and decrypt with correct output naming
        self.log(f"Starting decryption in directory: {search_dir}")
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".encrypted.mp4") or file.endswith(".encrypted.m4a"):
                    if self.stop_event.is_set():
                        self.log("Stopped during decryption.")
                        return
                    in_path = os.path.join(root, file)
                    base_name = file.replace(".encrypted", "")
                    out_path = os.path.join(root, base_name)
                    if os.path.exists(out_path):
                        self.log(f"Skipping already decrypted: {base_name}")
                        continue
                    cmd = [self.ffmpeg_path, "-nostdin", "-loglevel", "error", "-decryption_key", decryption_key, "-i", in_path, "-c", "copy", out_path]
                    self.log(f"Decrypting: {file} -> {base_name}")
                    try:
                        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        self.ffmpeg_processes.append(proc)
                        stdout, stderr = proc.communicate()
                        if stdout:
                            for line in stdout.splitlines():
                                self.log(line)
                        if stderr:
                            for line in stderr.splitlines():
                                self.log(f"[ffmpeg] {line}")
                        if self.stop_event.is_set():
                            self.log("Terminated ffmpeg during decryption.")
                            return
                        if proc.returncode != 0:
                            self.log(f"Error decrypting {file}: ffmpeg exited with code {proc.returncode}")
                        elif not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                            self.log(f"Decryption failed: Output file not created or empty for {file}")
                        else:
                            self.log(f"Decrypted: {out_path}")
                    except Exception as e:
                        self.log(f"Error running ffmpeg: {e}")

    def combine_files(self, search_dir):
        from pathvalidate import sanitize_filename
        final_suffix = ""
        id_to_title_map = {}

        # Find and load the ID-to-title map
        for dirpath, _, filenames in os.walk(search_dir):
            if "id_to_title.json" in filenames:
                map_file_path = os.path.join(dirpath, "id_to_title.json")
                try:
                    with open(map_file_path, "r", encoding="utf-8") as f:
                        id_to_title_map = json.load(f)
                    self.log(f"Loaded title mapping from {map_file_path}")
                except Exception as e:
                    self.log(f"Error loading title map: {e}")
                break # Assume one map per run

        self.log(f"Starting combination in directory: {search_dir}")
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                # Ensure we only process decrypted .mp4 files that are not still in their original encrypted form
                # and have not yet been combined (checked later by os.path.exists(final_output_path)).
                # This fixes the logical error when final_suffix is empty.
                if file.endswith(".mp4") and ".encrypted" not in file:
                    file_id = file[:-4]
                    mp4_path = os.path.join(root, file)
                    m4a_path = os.path.join(root, f"{file_id}.m4a")

                    # Determine final name
                    lecture_title = id_to_title_map.get(file_id)
                    if lecture_title:
                        final_base_name = sanitize_filename(lecture_title)
                        self.log(f"Found title for ID {file_id}: '{lecture_title}'")
                    else:
                        final_base_name = file_id
                        self.log(f"No title found for ID {file_id}, using ID as name.")

                    final_output_name = f"{final_base_name}{final_suffix}.mp4"
                    final_output_path = os.path.join(root, final_output_name)

                    if os.path.exists(mp4_path) and os.path.exists(m4a_path):
                        if os.path.exists(final_output_path):
                            self.log(f"Skipping already combined file: {final_output_name}")
                            continue

                        self.log(f"Combining and fixing sync for: {file}")
                        cmd = [self.ffmpeg_path, "-nostdin", "-loglevel", "error", "-i", mp4_path, "-i", m4a_path, "-copyts", "-start_at_zero", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy", "-shortest", final_output_path]
                        try:
                            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            self.ffmpeg_processes.append(proc)
                            stdout, stderr = proc.communicate()
                            if proc.returncode == 0 and os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                                self.log(f"  > Success! Cleaning up temporary files.")
                                # Clean up decrypted and encrypted files
                                encrypted_mp4_path = os.path.join(root, f"{file_id}.encrypted.mp4")
                                encrypted_m4a_path = os.path.join(root, f"{file_id}.encrypted.m4a")
                                for f_path in [mp4_path, m4a_path, encrypted_mp4_path, encrypted_m4a_path]:
                                    if os.path.exists(f_path):
                                        try:
                                            os.remove(f_path)
                                        except Exception as e:
                                            self.log(f"Error deleting {f_path}: {e}")
                                self.log(f"Combined: {final_output_path}")

                                # Rename associated subtitle files
                                srt_files = [f for f in os.listdir(root) if f.startswith(final_base_name) and f.endswith(".srt")]
                                for srt_file in srt_files:
                                    lang_part_match = re.search(r'(_[a-z]{2,3}(?:_[A-Z]{2,3})?).srt$', srt_file)
                                    if lang_part_match:
                                        lang_part = lang_part_match.group(1)
                                        old_srt_path = os.path.join(root, srt_file)
                                        new_srt_name = f"{final_base_name}{final_suffix}{lang_part}.srt"
                                        new_srt_path = os.path.join(root, new_srt_name)
                                        try:
                                            if os.path.exists(old_srt_path):
                                                os.rename(old_srt_path, new_srt_path)
                                                self.log(f"Renamed caption to: {new_srt_name}")
                                        except Exception as e:
                                            self.log(f"Error renaming caption {srt_file}: {e}")
                            else:
                                self.log(f"  > ERROR: ffmpeg failed to combine {file}. Temporary files were NOT deleted.")
                                if stderr:
                                    for line in stderr.splitlines():
                                        self.log(f"[ffmpeg] {line}")
                        except Exception as e:
                            self.log(f"Error running ffmpeg: {e}")
                    else:
                        self.log(f"Skipping combine for {file} - missing video or audio part.")

    def cleanup_temp_folders(self, search_dir):
        self.log(f"Scanning for 'temp' folders in {search_dir}...")
        for root, dirs, files in os.walk(search_dir):
            if 'temp' in dirs:
                temp_path = os.path.join(root, 'temp')
                try:
                    shutil.rmtree(temp_path)
                    self.log(f"Removed temporary directory: {temp_path}")
                except Exception as e:
                    self.log(f"Error removing temp directory {temp_path}: {e}")

def main():
    root = tk.Tk()
    app = UdemyDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
