import tkinter as tk
from tkinter import messagebox, simpledialog
import json
import os
import subprocess

class Kiosk(tk.Tk):
    def __init__(self, skin_folder='skins'):
        super().__init__()
        self.title('Kiosk Application')
        self.geometry('1024x768')  # Set the resolution
        self.attributes('-fullscreen', True)  # Start in fullscreen

        # Exit button on the top-left corner
        self.exit_button = tk.Button(self, text="X", command=self.destroy, bg="red", fg="white")
        self.exit_button.place(x=10, y=10, width=30, height=30)

        self.skin_folder = skin_folder
        self.current_skin = 'default_skin.json'
        self.load_skin(self.current_skin)

        self.hamburger_menu = tk.Menu(self, tearoff=0)
        self.build_hamburger_menu()

        self.bind("<Button-3>", self.show_hamburger_menu)
        self.ps4_process = None
        self.main_process = None
        self.draw_title()


    # ... rest of the class remains unchanged

    def load_skin(self, skin_file):
        with open(os.path.join(self.skin_folder, skin_file), 'r') as file:
            self.skin = json.load(file)
        self.draw_buttons()

    def draw_buttons(self):
        button_width = 170
        button_height = 150
        spacing = 50
        total_width = 3*button_width + 2*spacing
        button_font = ('Arial', 36)  # This uses Arial font with a size of 36. Adjust as needed.
    
        # Starting x-coordinate to center the three buttons
        start_x = (1024 - total_width) // 2
    
        # Vertically center the buttons
        y = (768 - button_height) // 2
    
        # Blue (PS4) button
        self.ps4_button = tk.Button(self, text='PS4', command=self.ps4_clicked,
                                    bg='blue', fg='white',
                                    width=button_width, height=button_height, font=button_font)
        self.ps4_button.place(x=start_x, y=y, width=button_width, height=button_height)
        
        # Red (STOP) button
        self.stop_button = tk.Button(self, text='STOP', command=self.stop_clicked,
                                     bg='red', fg='white',
                                     width=button_width, height=button_height, font=button_font)
        self.stop_button.place(x=start_x + button_width + spacing, y=y, width=button_width, height=button_height)
        
        # Green (TRACK) button
        self.track_button = tk.Button(self, text='TRACK', command=self.track_clicked,
                                      bg='green', fg='white',
                                      width=button_width, height=button_height, font=button_font)
        self.track_button.place(x=start_x + 2*button_width + 2*spacing, y=y, width=button_width, height=button_height)

    def build_hamburger_menu(self):
        skins_menu = tk.Menu(self.hamburger_menu, tearoff=0)

        for skin_file in os.listdir(self.skin_folder):
            if skin_file.endswith('.json'):
                skins_menu.add_command(label=skin_file, command=lambda s=skin_file: self.load_skin(s))

        self.hamburger_menu.add_cascade(label="Skins", menu=skins_menu)
        self.hamburger_menu.add_command(label="About", command=self.show_about)

    def show_hamburger_menu(self, event):
        self.hamburger_menu.post(event.x_root, event.y_root)

    def show_about(self):
        about_window = tk.Toplevel(self)
        about_window.geometry('300x200')
        about_window.title('About Wingman')
        tk.Label(about_window, text="WINGMAN", font=('Arial', 14, 'bold')).pack(pady=20)
        tk.Label(about_window, text="Kevin Finisterre").pack()
        tk.Label(about_window, text="John Cherbini").pack()

    def ps4_clicked(self):
        if self.main_process and self.main_process.poll() is None:
            self.main_process.terminate()
        self.ps4_process = subprocess.Popen(['python3', 'ps4.py'])
    
    def track_clicked(self):
        if self.ps4_process and self.ps4_process.poll() is None:
            self.ps4_process.terminate()
        self.main_process = subprocess.Popen(['python3', 'main.py'])
    
    def stop_clicked(self):
        if self.ps4_process and self.ps4_process.poll() is None:
            self.ps4_process.terminate()
    
        if self.main_process and self.main_process.poll() is None:
            self.main_process.terminate()
    def draw_title(self):
        custom_font = ('8-bit\ Arcade\ In.ttf', 48)  # Replace 'YourFontName' with the name of the font you chose
        tk.Label(self, text="WINGMAN", font=custom_font, bg='black', fg='white').place(x=320, y=100)


if __name__ == "__main__":
    kiosk_app = Kiosk()
    kiosk_app.mainloop()
