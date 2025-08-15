import tkinter as tk
from tkinter import messagebox
import os
import shutil

# ---------------------
# FILE ORGANIZER LOGIC
# ---------------------
def organize_files():
    try:
        folder_path = "C:/path/to/your/folder"  # Change this
        file_types = {
            "Images": [".jpg", ".jpeg", ".png", ".gif"],
            "Documents": [".pdf", ".docx", ".txt"],
            "Videos": [".mp4", ".mov", ".avi"]
        }

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                for category, extensions in file_types.items():
                    if filename.lower().endswith(tuple(extensions)):
                        category_folder = os.path.join(folder_path, category)
                        os.makedirs(category_folder, exist_ok=True)
                        shutil.move(file_path, os.path.join(category_folder, filename))
                        break

        messagebox.showinfo("✅ Success", "Files organized successfully!")

    except Exception as e:
        messagebox.showerror("❌ Error", f"Something went wrong: {e}")

# ---------------------
# MODERN UI
# ---------------------
root = tk.Tk()
root.title("Akovian File Organizer")
root.geometry("600x400")
root.configure(bg="#0F172A")  # Dark blue-gray background
root.resizable(False, False)

# Center window on screen
root.update_idletasks()
w = root.winfo_screenwidth()
h = root.winfo_screenheight()
size = tuple(int(_) for _ in root.geometry().split('+')[0].split('x'))
x = w//2 - size[0]//2
y = h//2 - size[1]//2
root.geometry(f"{size[0]}x{size[1]}+{x}+{y}")

# Title label
title_label = tk.Label(
    root, 
    text="Akovian File Manager",
    font=("Segoe UI", 20, "bold"),
    fg="#E2E8F0",
    bg="#0F172A"
)
title_label.pack(pady=40)

# Glassy button style
def on_enter(e):
    e.widget["bg"] = "#38BDF8"
    e.widget["fg"] = "#0F172A"

def on_leave(e):
    e.widget["bg"] = "#1E293B"
    e.widget["fg"] = "#E2E8F0"

organize_button = tk.Button(
    root,
    text="⚡ Organize Files",
    command=organize_files,
    font=("Segoe UI", 14, "bold"),
    bg="#1E293B",
    fg="#E2E8F0",
    activebackground="#38BDF8",
    activeforeground="#0F172A",
    relief="flat",
    width=20,
    height=2
)
organize_button.pack(pady=20)
organize_button.bind("<Enter>", on_enter)
organize_button.bind("<Leave>", on_leave)

# Footer
footer = tk.Label(
    root,
    text="Made by Akovian Technologies",
    font=("Segoe UI", 10),
    fg="#94A3B8",
    bg="#0F172A"
)
footer.pack(side="bottom", pady=10)

root.mainloop()