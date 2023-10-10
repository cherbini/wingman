import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import json
import os
import subprocess
from dynamixel_controller import DynamixelController


class Kiosk(tk.Tk):
    def __init__(self, dynamixel_controller, skin_folder='skins'):
        super().__init__()
        self.dynamixel_controller = dynamixel_controller
        self.title('Kiosk Application')
        self.geometry('1024x768')  # Set the resolution
        self.attributes('-fullscreen', True)  # Start in fullscreen

        # Exit button on the top-left corner
        self.exit_button = tk.Button(self, text="X", command=self.destroy, bg="red", fg="white")
        self.exit_button.place(x=10, y=10, width=30, height=30)

        self.skin_folder = skin_folder
        self.current_skin = 'default_skin.json'
        self.load_skin(self.current_skin)

       # Replaced "Copy" and "Clear" buttons with "Save to output.txt" button
        self.save_button = tk.Button(self, text="Save to output.txt", command=self.save_to_output_txt)
        self.save_button.place(x=50, y=650, width=200, height=30)  # Adjusted width to fit the new text

        self.hamburger_menu = tk.Menu(self, tearoff=0)
        self.build_hamburger_menu()

        self.bind("<Button-3>", self.show_hamburger_menu)
        self.ps4_process = None
        self.main_process = None
        self.draw_title()
        # Add Text widget for stdout display
        self.stdout_display = tk.Text(self, height=5, wrap=tk.WORD, font=("Arial", 12), bg='gray90', fg='black', bd=0,
                                      highlightthickness=0, state=tk.DISABLED)
        self.stdout_display.place(x=50, y=500, width=924)  # Adjust the y-position to move the widget upwards

        # Store process outputs in a buffer
        self.output_buffer = []
        self.stdout_frame = tk.Frame(self)
        self.stdout_frame.place(x=50, y=500, width=924, height=140)  # Adjusted height to accommodate scrollbar

        self.scrollbar = tk.Scrollbar(self.stdout_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.stdout_display = tk.Text(self.stdout_frame, height=5, wrap=tk.WORD, font=("Arial", 12), bg='gray90', fg='black', bd=0, highlightthickness=0, state=tk.DISABLED, yscrollcommand=self.scrollbar.set)
        self.stdout_display.pack(fill=tk.BOTH, expand=1)
        
        self.scrollbar.config(command=self.stdout_display.yview)

        # Add the Pan PIDs frame and sliders
        self.pan_pids_frame = ttk.LabelFrame(self, text="Pan PIDs", padding=(10, 5))
        self.pan_pids_frame.place(x=750, y=500, width=220, height=150)

        # Add the Tilt PIDs frame and sliders
        self.tilt_pids_frame = ttk.LabelFrame(self, text="Tilt PIDs", padding=(10, 5))
        self.tilt_pids_frame.place(x=750, y=660, width=220, height=150)

        self.pan_kp_slider = tk.Scale(self.pan_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Kp", command=self.update_pan_pid)
        self.pan_ki_slider = tk.Scale(self.pan_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Ki", command=self.update_pan_pid)
        self.pan_kd_slider = tk.Scale(self.pan_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Kd", command=self.update_pan_pid)
        
        self.tilt_kp_slider = tk.Scale(self.tilt_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Kp", command=self.update_tilt_pid)
        self.tilt_ki_slider = tk.Scale(self.tilt_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Ki", command=self.update_tilt_pid)
        self.tilt_kd_slider = tk.Scale(self.tilt_pids_frame, from_=0, to_=10, resolution=0.1, orient=tk.HORIZONTAL, label="Kd", command=self.update_tilt_pid)
        # Initialize the dynamixel controller
        self.dynamixel_controller = DynamixelController("/dev/ttyUSB0", 1000000, 1, 2)  # Adjust parameters if needed

    # Adjust the placement and size of the Pan PIDs frame and sliders
    # Adjust the placement and size of the Pan PIDs frame and sliders
    def draw_pid_sliders(self):
        right_padding = 50  # Padding from the right edge
        slider_width = 220
        slider_height = (self.winfo_height() - 2 * right_padding) / 2
    
        # Pan PIDs frame and sliders
        self.pan_pids_frame.place(x=self.winfo_width() - slider_width - right_padding, y=right_padding, width=slider_width, height=slider_height)
        self.pan_kp_slider.pack(fill=tk.BOTH, expand=True)
        self.pan_ki_slider.pack(fill=tk.BOTH, expand=True)
        self.pan_kd_slider.pack(fill=tk.BOTH, expand=True)
    
        # Tilt PIDs frame and sliders
        self.tilt_pids_frame.place(x=self.winfo_width() - slider_width - right_padding, y=self.winfo_height()/2 + right_padding/2, width=slider_width, height=slider_height)
        self.tilt_kp_slider.pack(fill=tk.BOTH, expand=True)
        self.tilt_ki_slider.pack(fill=tk.BOTH, expand=True)
        self.tilt_kd_slider.pack(fill=tk.BOTH, expand=True)

    def track_clicked(self):
        # Set the slider values to the current PID values before starting tracking
        self.pan_kp_slider.set(self.dynamixel_controller.pan_pid.kp)
        self.pan_ki_slider.set(self.dynamixel_controller.pan_pid.ki)
        self.pan_kd_slider.set(self.dynamixel_controller.pan_pid.kd)

        self.tilt_kp_slider.set(self.dynamixel_controller.tilt_pid.kp)
        self.tilt_ki_slider.set(self.dynamixel_controller.tilt_pid.ki)
        self.tilt_kd_slider.set(self.dynamixel_controller.tilt_pid.kd)


    def save_to_output_txt(self):
        """Save the contents of the stdout_display Text widget to output.txt."""
        content = self.stdout_display.get(1.0, tk.END)
        with open("output.txt", "w") as file:
            file.write(content)

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
        #start_x = (1024 - total_width) // 2
        start_x = 50
    
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

    def copy_to_clipboard(self):
        """Copy the contents of the stdout_display Text widget to the clipboard."""
        content = self.stdout_display.get(1.0, tk.END)
        self.clipboard_clear()
        self.clipboard_append(content)

    def clear_stdout_display(self):
        """Clear the contents of the stdout_display Text widget."""
        self.stdout_display.config(state=tk.NORMAL)
        self.stdout_display.delete(1.0, tk.END)
        self.stdout_display.config(state=tk.DISABLED)

    def display_pid_values(self):
        # Fetch the current PID values
        pan_kp = self.dynamixel_controller.pan_pid.kp
        pan_ki = self.dynamixel_controller.pan_pid.ki
        pan_kd = self.dynamixel_controller.pan_pid.kd
    
        tilt_kp = self.dynamixel_controller.tilt_pid.kp
        tilt_ki = self.dynamixel_controller.tilt_pid.ki
        tilt_kd = self.dynamixel_controller.tilt_pid.kd
    
        # Prepare the message string
        message = f"Pan PID Values: Kp={pan_kp}, Ki={pan_ki}, Kd={pan_kd}\n"
        message += f"Tilt PID Values: Kp={tilt_kp}, Ki={tilt_ki}, Kd={tilt_kd}"
    
        # Append to the stdout_display
        self.append_to_stdout(message)

    def append_to_stdout(self, line):
        """Append a line of text to the Text widget and ensure only the last 50 lines are visible."""
        self.output_buffer.append(line)
        while len(self.output_buffer) > 50:  # Keep only the last 50 lines
            self.output_buffer.pop(0)
        self.stdout_display.config(state=tk.NORMAL)
        self.stdout_display.delete(1.0, tk.END)
        self.stdout_display.insert(tk.END, '\n'.join(self.output_buffer))
        self.stdout_display.config(state=tk.DISABLED)
        self.stdout_display.yview(tk.END)  # Automatically scroll to the end

    def update_pan_pid(self, event=None):
        kp = self.pan_kp_slider.get()
        ki = self.pan_ki_slider.get()
        kd = self.pan_kd_slider.get()
        self.dynamixel_controller.pan_pid.set_parameters(kp, ki, kd)
        self.display_pid_values()


    def update_tilt_pid(self, event=None):
        kp = self.tilt_kp_slider.get()
        ki = self.tilt_ki_slider.get()
        kd = self.tilt_kd_slider.get()
        self.dynamixel_controller.tilt_pid.set_parameters(kp, ki, kd)
        self.display_pid_values()


    def update_stdout_display(self):
        try:
            if self.ps4_process and self.ps4_process.poll() is None:
                line = self.ps4_process.stdout.readline().strip()
                if line:
                    self.append_to_stdout(line)
            if self.main_process and self.main_process.poll() is None:
                line = self.main_process.stdout.readline().strip()
                if line:
                    self.append_to_stdout(line)
            self.after(100, self.update_stdout_display)
        except Exception as e:
            print("Error in update_stdout_display:", e)

    def ps4_clicked(self):
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if self.main_process and self.main_process.poll() is None:
            self.main_process.terminate()
        self.ps4_process = subprocess.Popen(['python3', 'ps4.py'], env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
        self.update_stdout_display()

    def track_clicked(self):
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if self.ps4_process and self.ps4_process.poll() is None:
            self.ps4_process.terminate()
        self.main_process = subprocess.Popen(['python3', 'main.py'], env=env, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
        self.update_stdout_display()

    def stop_clicked(self):
        if self.ps4_process and self.ps4_process.poll() is None:
            self.ps4_process.terminate()
    
        if self.main_process and self.main_process.poll() is None:
            self.main_process.terminate()

    def draw_title(self):
        custom_font = ('8-bit\ Arcade\ In.ttf', 48)
    
        # Get coordinates and dimensions of the STOP button
        stop_button_x = self.stop_button.winfo_x()
        stop_button_width = self.stop_button.winfo_width()
    
        # Calculate the center point of the STOP button
        stop_button_center_x = stop_button_x + stop_button_width / 2
    
        # Use a Label widget to calculate the width of the "WINGMAN" text using the custom font
        temp_label = tk.Label(self, text="WINGMAN", font=custom_font)
        temp_label.update_idletasks()
        title_width = temp_label.winfo_width()
        temp_label.destroy()
    
        # Calculate the starting x-coordinate for the "WINGMAN" title, adding a slight adjustment to the right.
        adjustment = 190  # Increase or decrease this value to further adjust the position.
        title_x = stop_button_center_x - title_width / 2 + adjustment
        title_y = 70  # Adjust this value to position the title at a desired height
    
        tk.Label(self, text="WINGMAN", font=custom_font, bg='black', fg='white').place(x=title_x, y=title_y)


if __name__ == "__main__":
    # Assuming you have imported the DynamixelController at the top of kiosk.py
    # Instantiate the dynamixel controller first
    dynamixel_controller = DynamixelController("/dev/ttyUSB0", 1000000, 1, 2)

    # Now, instantiate the Kiosk app with the dynamixel controller
    kiosk_app = Kiosk(dynamixel_controller)
    kiosk_app.after(100, kiosk_app.draw_pid_sliders)  # Delay of 100 milliseconds
    kiosk_app.mainloop()


