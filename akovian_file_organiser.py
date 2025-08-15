# akovian_file_organizer.py
# PyQt5 "Akovian File Organizer" — Windows 11 Dark style
# - Responsive, glass/dark look
# - High-DPI crisp scaling
# - Zoom control (Ctrl+= / Ctrl+- / Ctrl+0)
# - Drag & drop folder
# - Ignore patterns
# - Save/Load profiles (JSON)
# - Preview (dry-run) mode
# - Zip archive output
# - Undo last move
# - Duplicate finder (basic, hash-based)
# - Bulk rename (prefix/suffix)
# Run: python akovian_file_organizer.py

import sys, os, re, json, shutil, hashlib, zipfile
from datetime import datetime
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

# -----------------------------
# Backend helpers
# -----------------------------
def default_file_types():
    return {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic"],
        "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".md"],
        "Videos": [".mp4", ".mov", ".avi", ".mkv", ".webm"],
        "Music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"]
    }

def make_backup_folder(base_folder: str) -> str:
    backups = os.path.join(base_folder, "_akovian_backups")
    os.makedirs(backups, exist_ok=True)
    return backups

def backup_file(src_path: str, backups_folder: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(src_path)
    dst = os.path.join(backups_folder, f"{stamp}__{filename}")
    shutil.copy2(src_path, dst)
    return dst

def match_ignored(filename: str, patterns: list) -> bool:
    """Return True if filename matches any ignore pattern (supports wildcards: *, ?)."""
    for p in patterns:
        # convert glob-like to regex
        r = "^" + re.escape(p).replace(r"\*", ".*").replace(r"\?", ".") + "$"
        if re.match(r, filename, flags=re.IGNORECASE):
            return True
    return False

def organize_folder(folder_path: str, file_types: dict, ignore_patterns: list, dry_run=False, log=None):
    """
    Organize files in folder_path according to file_types.
    Returns (moved_records, backups_folder).
    moved_records: [(orig_full_path, new_full_path)]
    """
    if log is None:
        log = lambda *a, **k: None

    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError("Selected path is not a folder")

    backups_folder = make_backup_folder(folder_path)
    moved_records = []

    for entry in folder.iterdir():
        if entry.is_file() and entry.parent.name != "_akovian_backups":
            filename = entry.name
            if match_ignored(filename, ignore_patterns):
                log(f"Skipped (ignored): {filename}")
                continue

            lower = filename.lower()
            category = None
            for cat, exts in file_types.items():
                if any(lower.endswith(ext) for ext in exts):
                    category = cat
                    break
            if category is None:
                category = "Others"

            target_dir = folder / category
            target_dir.mkdir(exist_ok=True)

            # find non-colliding name
            candidate = target_dir / filename
            cnt = 1
            while candidate.exists():
                candidate = target_dir / f"{candidate.stem}_{cnt}{candidate.suffix}"
                cnt += 1

            if dry_run:
                log(f"[Preview] Would move: {filename} → {category}/{candidate.name}")
                moved_records.append((str(entry), str(candidate)))
            else:
                backup_path = backup_file(str(entry), backups_folder)
                shutil.move(str(entry), str(candidate))
                moved_records.append((str(entry), str(candidate)))
                log(f"Moved: {filename} → {category}  (backup: {os.path.basename(backup_path)})")

    return moved_records, backups_folder

def undo_moves(moved_records: list, log=None):
    if log is None:
        log = lambda *a, **k: None

    success = 0
    fail = 0
    for orig, new in reversed(moved_records):
        try:
            os.makedirs(os.path.dirname(orig), exist_ok=True)
            if os.path.exists(new):
                if os.path.exists(orig):
                    base, ext = os.path.splitext(orig)
                    idx = 1
                    candidate = f"{base}_restored{idx}{ext}"
                    while os.path.exists(candidate):
                        idx += 1
                        candidate = f"{base}_restored{idx}{ext}"
                    shutil.move(new, candidate)
                    log(f"Restored: {os.path.basename(new)} → {os.path.basename(candidate)} (orig existed)")
                else:
                    shutil.move(new, orig)
                    log(f"Restored: {os.path.basename(new)} → {os.path.basename(orig)}")
                success += 1
            else:
                fail += 1
                log(f"Undo failed (missing): {new}")
        except Exception as e:
            fail += 1
            log(f"Undo error for {new}: {e}")
    return success, fail

def hash_file(path: str, block_size=65536):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

def find_duplicates(folder_path: str, ignore_patterns: list, log=None):
    """Return dict {hash: [paths...]} for files with identical content (size>0)."""
    if log is None:
        log = lambda *a, **k: None

    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError("Folder not found")

    seen = {}
    for entry in folder.iterdir():
        if entry.is_file() and entry.parent.name != "_akovian_backups":
            name = entry.name
            if match_ignored(name, ignore_patterns):
                continue
            try:
                if entry.stat().st_size == 0:
                    continue
                file_hash = hash_file(str(entry))
                seen.setdefault(file_hash, []).append(str(entry))
            except Exception as e:
                log(f"Hash error {name}: {e}")

    duplicates = {h: paths for h, paths in seen.items() if len(paths) > 1}
    return duplicates

def bulk_rename(paths: list, prefix="", suffix="", log=None, dry_run=False):
    if log is None:
        log = lambda *a, **k: None

    results = []
    for p in paths:
        parent, name = os.path.dirname(p), os.path.basename(p)
        stem, ext = os.path.splitext(name)
        new_name = f"{prefix}{stem}{suffix}{ext}"
        new_path = os.path.join(parent, new_name)
        if dry_run:
            log(f"[Preview] {name} → {new_name}")
        else:
            cnt = 1
            candidate = new_path
            while os.path.exists(candidate) and candidate.lower() != p.lower():
                stem2, ext2 = os.path.splitext(new_name)
                candidate = os.path.join(parent, f"{stem2}_{cnt}{ext2}")
                cnt += 1
            os.rename(p, candidate)
            log(f"Renamed: {name} → {os.path.basename(candidate)}")
            new_path = candidate
        results.append((p, new_path))
    return results

def zip_folder(folder_path: str, output_zip: str, log=None):
    if log is None:
        log = lambda *a, **k: None

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder_path):
            # skip backups folder
            if os.path.basename(root) == "_akovian_backups":
                continue
            for f in files:
                fp = os.path.join(root, f)
                arc = os.path.relpath(fp, folder_path)
                z.write(fp, arc)
    log(f"Zipped to: {output_zip}")

# -----------------------------
# UI
# -----------------------------
class DropLineEdit(QtWidgets.QLineEdit):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                self.setText(p)
                break

class DuplicatesDialog(QtWidgets.QDialog):
    def __init__(self, duplicates: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files")
        self.resize(700, 420)
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel("These files appear to be duplicates (same content hash).")
        layout.addWidget(info)
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(self.list.ExtendedSelection)
        layout.addWidget(self.list)
        for h, paths in duplicates.items():
            self.list.addItem(f"— Hash: {h[:12]} —")
            for p in paths:
                self.list.addItem(f"    {p}")
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)

class RenameDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Rename")
        self.resize(420, 160)
        v = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.prefix = QtWidgets.QLineEdit()
        self.suffix = QtWidgets.QLineEdit()
        self.preview = QtWidgets.QCheckBox("Preview (no changes)")
        form.addRow("Prefix:", self.prefix)
        form.addRow("Suffix:", self.suffix)
        v.addLayout(form)
        v.addWidget(self.preview)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

class GlassWindow(QtWidgets.QWidget):
    zoomChanged = QtCore.pyqtSignal(float)  # for live UI scaling

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Akovian File Organizer — Win11 Dark")
        self.resize(900, 620)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # app state
        self.last_moved_records = []
        self.last_backups_folder = None
        self.file_types = default_file_types()
        self.zoom_factor = 1.0  # user zoom

        self.setup_ui()
        self.apply_style()
        self.center()
        self.install_shortcuts()

    # ---------- window chrome ----------
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if hasattr(self, "_drag_pos") and e.buttons() & QtCore.Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)
            e.accept()

    def center(self):
        geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move((geo.width()-self.width())//2, (geo.height()-self.height())//2)

    # ---------- UI ----------
    def setup_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)

        frame = QtWidgets.QFrame()
        frame.setObjectName("glass")
        fvl = QtWidgets.QVBoxLayout(frame)
        fvl.setContentsMargins(18, 18, 18, 18)
        fvl.setSpacing(12)

        # titlebar
        titlebar = QtWidgets.QHBoxLayout()
        ttl = QtWidgets.QLabel("Akovian File Organizer")
        ttl.setObjectName("title")
        sub = QtWidgets.QLabel("Windows 11 • Dark • Organize • Backup • Undo • Zip • Duplicates • Rename")
        sub.setObjectName("subtitle")
        tl = QtWidgets.QVBoxLayout()
        tl.addWidget(ttl)
        tl.addWidget(sub)
        titlebar.addLayout(tl)
        titlebar.addStretch()

        btn_min = QtWidgets.QPushButton("—"); btn_min.setFixedSize(30, 30)
        btn_max = QtWidgets.QPushButton("▢"); btn_max.setFixedSize(30, 30)
        btn_close = QtWidgets.QPushButton("✕"); btn_close.setFixedSize(30, 30)
        for b in (btn_min, btn_max, btn_close):
            b.setObjectName("winbtn")
        btn_min.clicked.connect(self.showMinimized)
        btn_max.clicked.connect(self.on_max_restore)
        btn_close.clicked.connect(self.close)
        titlebar.addWidget(btn_min); titlebar.addWidget(btn_max); titlebar.addWidget(btn_close)
        fvl.addLayout(titlebar)

        # top controls
        top = QtWidgets.QHBoxLayout()
        self.path = DropLineEdit()
        self.path.setPlaceholderText("Drop a folder here or click Browse…")
        self.path.setReadOnly(True)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self.on_browse)

        self.ignore = QtWidgets.QLineEdit()
        self.ignore.setPlaceholderText("Ignore patterns (comma-separated, e.g. *.tmp,Thumbs.db)")
        self.preview = QtWidgets.QCheckBox("Preview only (dry-run)")
        self.preview.setChecked(False)

        top.addWidget(self.path, 3)
        top.addWidget(browse, 0)
        top.addWidget(self.ignore, 3)
        top.addWidget(self.preview, 0)
        fvl.addLayout(top)

        # main area split: left actions / right log
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        left = QtWidgets.QFrame(); lv = QtWidgets.QVBoxLayout(left); lv.setSpacing(10)
        right = QtWidgets.QFrame(); rv = QtWidgets.QVBoxLayout(right)

        # action buttons (left)
        self.btn_org = QtWidgets.QPushButton("⚡ Organize")
        self.btn_undo = QtWidgets.QPushButton("↶ Undo Last")
        self.btn_zip = QtWidgets.QPushButton("🗜 Zip Folder")
        self.btn_dups = QtWidgets.QPushButton("🔁 Find Duplicates")
        self.btn_rename = QtWidgets.QPushButton("✎ Bulk Rename")
        for b in (self.btn_org, self.btn_undo, self.btn_zip, self.btn_dups, self.btn_rename):
            b.setObjectName("action")
            b.setMinimumHeight(40)

        self.btn_org.clicked.connect(self.on_organize)
        self.btn_undo.clicked.connect(self.on_undo)
        self.btn_zip.clicked.connect(self.on_zip)
        self.btn_dups.clicked.connect(self.on_duplicates)
        self.btn_rename.clicked.connect(self.on_bulk_rename)
        self.btn_undo.setEnabled(False)

        # zoom controls
        zoom_row = QtWidgets.QHBoxLayout()
        self.zoom_label = QtWidgets.QLabel("Zoom: 100%")
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoom_slider.setRange(75, 200)  # 75% to 200%
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(self.zoom_slider)

        lv.addWidget(self.btn_org)
        lv.addWidget(self.btn_undo)
        lv.addWidget(self.btn_zip)
        lv.addWidget(self.btn_dups)
        lv.addWidget(self.btn_rename)
        lv.addStretch(1)
        lv.addLayout(zoom_row)

        # right: progress + log + footer
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setTextVisible(True)
        self.status = QtWidgets.QLabel("Idle")
        self.log = QtWidgets.QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(260)

        # profile row
        prof_row = QtWidgets.QHBoxLayout()
        self.btn_save_prof = QtWidgets.QPushButton("Save Profile")
        self.btn_load_prof = QtWidgets.QPushButton("Load Profile")
        self.btn_save_prof.clicked.connect(self.on_save_profile)
        self.btn_load_prof.clicked.connect(self.on_load_profile)
        for b in (self.btn_save_prof, self.btn_load_prof):
            b.setObjectName("secondary")
        prof_row.addWidget(self.btn_save_prof)
        prof_row.addWidget(self.btn_load_prof)
        prof_row.addStretch()

        rv.addWidget(self.progress)
        rv.addWidget(self.status)
        rv.addWidget(self.log, 1)
        rv.addLayout(prof_row)

        split.addWidget(left); split.addWidget(right)
        split.setSizes([220, 680])
        fvl.addWidget(split, 1)

        # footer
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch()
        made = QtWidgets.QLabel("Made by Akovian Technologies")
        made.setObjectName("footer")
        footer.addWidget(made)
        fvl.addLayout(footer)

        main.addWidget(frame)

    def apply_style(self):
        # Win11-ish dark glass
        self.setStyleSheet("""
            QWidget { background: transparent; color: #E6EEF3; font-size: 12px; }
            QFrame#glass {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                             stop:0 rgba(18,21,27,235), stop:1 rgba(10,12,18,210));
                border-radius: 14px;
            }
            #title { font-weight: 800; font-size: 20px; color: #EAF6FF; }
            #subtitle { font-size: 11px; color: #9FB3C8; }
            #footer { font-size: 10px; color: #6D8D9E; }

            QPushButton#winbtn {
                background: rgba(255,255,255,8);
                border-radius: 6px; color: #B7CFE0; font-weight: 700;
            }
            QPushButton#winbtn:hover { background: rgba(255,255,255,14); }

            QLineEdit, QTextEdit {
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,12);
                border-radius: 10px; padding: 8px; color: #E6EEF3;
            }
            QCheckBox { color: #CFEFFE; }

            QPushButton#action {
                background: qlineargradient(x1:0, x2:1, stop:0 #2EE6FF, stop:1 #7C4DFF);
                color: #041025; border-radius: 10px; font-weight: 800;
            }
            QPushButton#action:hover {
                background: qlineargradient(x1:0, x2:1, stop:0 #54F0FF, stop:1 #9A67FF);
            }
            QPushButton#secondary {
                background: rgba(255,255,255,12); color: #C8EAF3;
                border-radius: 10px; font-weight: 700; padding: 6px 10px;
            }
            QPushButton#secondary:hover { background: rgba(255,255,255,16); }

            QProgressBar {
                background: rgba(255,255,255,8); border-radius: 7px; height: 14px; color: #E6EEF3;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, x2:1, stop:0 #2EE6FF, stop:1 #7C4DFF);
                border-radius: 7px;
            }
            QSplitter::handle { background: rgba(255,255,255,12); width: 2px; }
            QToolTip { color: #041025; background: #CFEFFE; border: 0px; }
        """)

    # ---------- shortcuts & zoom ----------
    def install_shortcuts(self):
        # Ctrl+O browse
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+O"), self, self.on_browse)
        # Ctrl+= zoom in, Ctrl+- zoom out, Ctrl+0 reset
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+="), self, lambda: self.adjust_zoom(10))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl++"), self, lambda: self.adjust_zoom(10))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+-"), self, lambda: self.adjust_zoom(-10))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+0"), self, lambda: self.set_zoom(100))

    def on_zoom_slider(self, val):
        self.set_zoom(val)

    def set_zoom(self, percent: int):
        percent = max(75, min(200, percent))
        self.zoom_factor = percent / 100.0
        self.zoom_label.setText(f"Zoom: {percent}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(percent)
        self.zoom_slider.blockSignals(False)

        # scale the base font; layouts adapt -> crisp on magnify
        base = self.font()
        base.setPointSizeF(12 * self.zoom_factor)
        self.setFont(base)
        # force relayout
        self.updateGeometry()
        for w in self.findChildren(QtWidgets.QWidget):
            w.updateGeometry()
            w.repaint()

    def adjust_zoom(self, delta_percent: int):
        self.set_zoom(int(self.zoom_factor * 100) + delta_percent)

    def on_max_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ---------- helpers ----------
    def log_line(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {text}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def get_ignore_patterns(self):
        raw = self.ignore.text().strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]

    # ---------- actions ----------
    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder", str(Path.home()))
        if folder:
            self.path.setText(folder)
            self.log_line(f"Selected: {folder}")

    def on_organize(self):
        folder = self.path.text().strip()
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "No folder", "Please select a valid folder to organize.")
            return
        self.progress.setValue(0); self.status.setText("Organizing…"); self.log.clear()
        QtWidgets.QApplication.processEvents()

        try:
            moved, backups = organize_folder(
                folder_path=folder,
                file_types=self.file_types,
                ignore_patterns=self.get_ignore_patterns(),
                dry_run=self.preview.isChecked(),
                log=self.log_line
            )
            self.last_moved_records = moved
            self.last_backups_folder = backups
            self.progress.setValue(100)
            if self.preview.isChecked():
                self.status.setText(f"Preview complete — {len(moved)} file(s) would move")
                QtWidgets.QMessageBox.information(self, "Preview", f"{len(moved)} file(s) would be moved.")
            else:
                self.status.setText(f"Done — {len(moved)} file(s) moved")
                QtWidgets.QMessageBox.information(self, "Done", f"Organized {len(moved)} file(s).")
            self.btn_undo.setEnabled(len(moved) > 0 and not self.preview.isChecked())
            if backups:
                self.log_line(f"Backups in: {backups}")
        except Exception as e:
            self.status.setText("Error"); self.log_line(f"Error: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def on_undo(self):
        if not self.last_moved_records:
            QtWidgets.QMessageBox.information(self, "Nothing to undo", "There is no recorded operation to undo.")
            return
        if QtWidgets.QMessageBox.question(self, "Undo last", "Restore files moved in the last operation?") != QtWidgets.QMessageBox.Yes:
            return
        ok, fail = undo_moves(self.last_moved_records, log=self.log_line)
        self.log_line(f"Undo completed: {ok} restored, {fail} failed")
        self.status.setText("Idle")
        self.last_moved_records = []
        self.btn_undo.setEnabled(False)

    def on_zip(self):
        folder = self.path.text().strip()
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save zip", os.path.join(folder, "organized.zip"), "Zip (*.zip)")
        if not out:
            return
        try:
            self.status.setText("Zipping…"); self.progress.setValue(0); QtWidgets.QApplication.processEvents()
            zip_folder(folder, out, log=self.log_line)
            self.progress.setValue(100); self.status.setText("Zip complete")
            QtWidgets.QMessageBox.information(self, "Zipped", f"Created: {out}")
        except Exception as e:
            self.status.setText("Error"); self.log_line(f"Zip error: {e}")
            QtWidgets.QMessageBox.critical(self, "Zip error", str(e))

    def on_duplicates(self):
        folder = self.path.text().strip()
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        self.status.setText("Scanning duplicates…"); self.progress.setValue(0); QtWidgets.QApplication.processEvents()
        d = find_duplicates(folder, self.get_ignore_patterns(), log=self.log_line)
        self.progress.setValue(100); self.status.setText("Idle")
        if not d:
            QtWidgets.QMessageBox.information(self, "Duplicates", "No duplicates found.")
        else:
            dlg = DuplicatesDialog(d, self); dlg.exec_()

    def on_bulk_rename(self):
        folder = self.path.text().strip()
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "No folder", "Select a folder first.")
            return

        # pick files to rename
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select files to rename", folder)
        if not files:
            return
        dlg = RenameDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            prefix = dlg.prefix.text()
            suffix = dlg.suffix.text()
            dry = dlg.preview.isChecked()
            self.status.setText("Renaming…"); self.progress.setValue(0)
            bulk_rename(files, prefix=prefix, suffix=suffix, log=self.log_line, dry_run=dry)
            self.progress.setValue(100); self.status.setText("Idle")
            if dry:
                QtWidgets.QMessageBox.information(self, "Preview", "Preview finished. No changes made.")
            else:
                QtWidgets.QMessageBox.information(self, "Renamed", "Bulk rename completed.")

    def on_save_profile(self):
        data = {
            "folder": self.path.text().strip(),
            "ignore_patterns": self.get_ignore_patterns(),
            "preview": self.preview.isChecked(),
            "zoom_percent": int(self.zoom_factor * 100),
            "file_types": self.file_types
        }
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Profile", str(Path.home() / "akovian_profile.json"), "JSON (*.json)")
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.log_line(f"Profile saved: {p}")
        QtWidgets.QMessageBox.information(self, "Saved", "Profile saved.")

    def on_load_profile(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Profile", str(Path.home()), "JSON (*.json)")
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.path.setText(data.get("folder", ""))
            self.ignore.setText(", ".join(data.get("ignore_patterns", [])))
            self.preview.setChecked(bool(data.get("preview", False)))
            z = int(data.get("zoom_percent", 100))
            self.set_zoom(z)
            ft = data.get("file_types")
            if isinstance(ft, dict):
                self.file_types = ft
            self.log_line(f"Profile loaded: {p}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load error", str(e))

# -----------------------------
# Run
# -----------------------------
def main():
    # High-DPI crisp scaling
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)

    # base font for scaling
    f = app.font(); f.setPointSize(12); app.setFont(f)

    w = GlassWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()