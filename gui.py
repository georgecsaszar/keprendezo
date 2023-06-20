import tkinter as tk
from tkinter import ttk, filedialog, Text, END, scrolledtext
import subprocess
import json
import time
import sys
import os
import PIL.Image
import math

from PIL.ExifTags import TAGS, GPSTAGS
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

os.environ["PATH"] += os.pathsep + '../build/ffmpeg/bin'

import ffmpeg
import re
from tqdm import tqdm
import shutil
import datetime
import numpy as np
from sklearn.cluster import DBSCAN
from math import radians, cos, sin, asin, sqrt

Image.MAX_IMAGE_PIXELS = None

# Define the selected directory path
selected_directory = None

# Define a function to select a directory path
def select_directory():
    global selected_directory
    selected_directory = filedialog.askdirectory()
    if selected_directory:
        directory_label.config(text=selected_directory)
    else:
        directory_label.config(text="")

def run_rename_script():
    def get_exif(file_path):
        try:
            exif = PIL.Image.open(file_path).getexif()
            if exif is not None:
                for (tag,value) in exif.items():
                    tag_name = TAGS.get(tag, tag)
                    if tag_name in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
                        # Validate date format
                        try:
                            datetime.datetime.strptime(value.split(' ')[0], "%Y:%m:%d")
                            return value
                        except ValueError:
                            return "dateerror"
        except PIL.UnidentifiedImageError:
            os.remove(file_path)
        return None

    def get_video_creation_date(file_path):
        try:
            probe = ffmpeg.probe(file_path)
            metadata = probe['streams'][0]['tags']
            if 'creation_time' in metadata:
                creation_date = metadata['creation_time']
                creation_date = creation_date.split('T')[0]  # This line extracts only the date (year, month, day) from the video file metadata
                return creation_date
        except (ffmpeg.Error, IndexError, KeyError):
            print(f"Unable to extract video creation date from the file at {file_path}. It might be corrupted.")
        return None

    def get_highest_suffix(similar_files):
        highest = 0
        for file in similar_files:
            match = re.search(r'\d+$', os.path.splitext(file)[0])
            if match:
                number = int(match.group())
                if number > highest:
                    highest = number
        return highest

    def rename_file(file_path, creation_date, no_exif=False, is_video=False):
        directory = os.path.dirname(file_path)
        filename, ext = os.path.splitext(os.path.basename(file_path))
        
        # Create a list of the regular expressions to match
        patterns = [
            r"\d{4}-\d{2}-\d{2}_pic \d+\.\w+",  # matches yyyy-mm-dd_pic x.ext
            r"\d{4}-\d{2}-\d{2}_vid \d+\.\w+",  # matches yyyy-mm-dd_vid x.ext
            r".*no exif.*",  # matches filename with no exif string
            r".*exif error.*"  # matches filename with exif error string
        ]
        
        # Check if the file name matches any of the patterns
        if any(re.fullmatch(pattern, filename + ext) for pattern in patterns):
            return  # If it does, don't rename the file
        
        if no_exif:
            new_base_name = filename + " - no exif"
        elif creation_date is None:
            new_base_name = filename + " - exif error"
        elif creation_date == "dateerror":
            new_base_name = filename + " - exif date error"
        else:
            creation_date = creation_date.split(' ')[0]  # This line extracts only the date (year, month, day) from the image file metadata
            new_base_name = creation_date.replace(':', '-').replace('/', '_').replace(',', ' ')
        
        suffix = "_vid" if is_video else "_pic"
        similar_files = [name for name in os.listdir(directory) if name.startswith(new_base_name + suffix)]
        highest_suffix = get_highest_suffix(similar_files)
        
        # Avoid adding suffix and highest_suffix for no exif and exif error files
        if "no exif" in new_base_name or "exif error" in new_base_name:
            new_file_name = f"{new_base_name}{ext}"
        else:
            new_file_name = f"{new_base_name}{suffix} {highest_suffix + 1}{ext}"
        
        new_file_path = os.path.join(directory, new_file_name)

        # If file already exists, skip renaming
        if os.path.exists(new_file_path):
            print(f"File {new_file_path} already exists, skipping...")
            return

        try:
            os.rename(file_path, new_file_path)
        except FileNotFoundError:
            pass


    def rename_files_in_dir(dir_path):
        file_count = sum([len(files) for r, d, files in os.walk(dir_path)])  # calculate total files
        pbar = tqdm(total=file_count, dynamic_ncols=True)  # initialize progress bar
        files_processed = 0
        for foldername, subfolders, filenames in os.walk(dir_path):
            for filename in filenames:
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.mov', '.mp4', '.mkv', '.avi')):
                    file_path = os.path.join(foldername, filename)
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        exif = get_exif(file_path)
                        rename_file(file_path, exif)
                    else:
                        creation_date = get_video_creation_date(file_path)
                        rename_file(file_path, creation_date, is_video=True)
                
                files_processed += 1
                progress = (files_processed / file_count) * 100
                progress_var.set(progress)
                progress1.update()
                pbar.update()  # update progress bar
        
        pbar.close()  # close progress bar
        progress_label1.config(text="Kesz")


    if not selected_directory:
            error_label.config(text="Valassz mappat eloszor")
            return
    
    progress_label1.config(text="Pill...")    
    rename_files_in_dir(selected_directory)
       

def run_process_script(radius):
    
    # Haversine formula for calculating distance between two points in a sphere given their longitudes and latitudes
    def haversine(lat1, lon1, lat2, lon2, progress_bar=None):
        """Calculate the great circle distance in kilometers between two points
        on the earth (specified in decimal degrees)"""
        # convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        km = 6367 * c

        # Update the progress bar
        if progress2 is not None:
            progress2.update()

        return km

    # Method to handle the GPS metadata
    def get_exif_data(image):
        exif_data = {}
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded == "GPSInfo":
                    gps_data = {}
                    for t in value:
                        sub_decoded = GPSTAGS.get(t, t)
                        gps_data[sub_decoded] = value[t]

                    exif_data[decoded] = gps_data
        return exif_data

    # Method to convert the GPS coordinates stored in the EXIF to degress in float format
    def convert_to_degress(value):
        deg, min, sec = value
        return deg + (min / 60.0) + (sec / 3600.0)

    def merge_dicts(dict1, dict2):
        """Function to merge two dictionaries"""
        files_final = {}

        for key in dict1:
            files_final[key] = {'year': dict1[key]['year'], 'month': dict1[key]['month']}
            if key in dict2:
                # 'cluster' field from the second dictionary is a number.
                files_final[key]['cluster'] = dict2[key]['cluster']
            else:
                # If the key is not in the second dictionary, add a 'gps' field and set it as False.
                files_final[key]['gps'] = False

        return files_final

    def process_files(file_dict, progress_bar=None):
        
        base_folder = selected_directory + '/Finished'
        i = 1

        while os.path.isdir(base_folder):
            base_folder = f'{selected_directory}/Finished{i}'
            i += 1
        
        os.makedirs(base_folder, exist_ok=True)

        month_names = {1: 'Januar', 2: 'Februar', 3: 'Marcius', 4: 'Aprilis', 
                       5: 'Majus', 6: 'Junius', 7: 'Julius', 8: 'Augusztus',
                       9: 'Szeptember', 10: 'Oktober', 11: 'November', 12: 'December'}

        total_files = len(file_dict)
        successful_moves = 0
        failed_moves = 0
        
        for file, data in tqdm(file_dict.items(), desc="Moving Files", unit="file", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"):
            
            year_folder = os.path.join(base_folder, str(data['year']))
            os.makedirs(year_folder, exist_ok=True)

            month_folder = os.path.join(year_folder, f"{str(data['month']).zfill(2)}-{month_names[data['month']]}")
            os.makedirs(month_folder, exist_ok=True)

            if 'cluster' in data:
                cluster_folder = os.path.join(month_folder, f'Helyszin{data["cluster"]}')
            else:
                cluster_folder = os.path.join(month_folder, 'Mix_kepek-hianyzo_gps')

            os.makedirs(cluster_folder, exist_ok=True)
            dest_folder = cluster_folder

            filename = os.path.basename(file)
            base_filename, ext = os.path.splitext(filename)

            new_dest_path = os.path.join(dest_folder, filename)
            suffix = 1

            while os.path.isfile(new_dest_path):
                new_filename = f"{base_filename}-{suffix}{ext}"
                new_dest_path = os.path.join(dest_folder, new_filename)
                suffix += 1

            # Try moving the file and track successful and failed moves
            try:
                shutil.move(file, new_dest_path)
                successful_moves += 1
                
            except Exception as e:
                print(f"Failed to move {file}: {str(e)}")
                failed_moves += 1

            # Update the progress bar
            if progress2 is not None:
                progress2.update()

        # Print out the statistics after all files have been processed
        print(f"Out of {total_files} files, {successful_moves} were moved successfully, and {failed_moves} failed to move.")
        progress2_var.set(100)
        progress2.update()
        progress_label2.config(text="Kesz")

    progress_label2.config(text="Pill...")

    radius_in_km = float(radius)

    # Initialize dictionaries for holding the data
    files_with_dates = {}
    files_with_gps = {}
    files_with_clusters = {}

    # List for holding the GPS coordinates
    gps_coords = []
    
    # Get the total number of files
    total_files = sum(len(files) for dirpath, dirs, files in os.walk(selected_directory))
    
    current_file_iter = 0
    # Traversing through the directory and processing each file
    for dirpath, dirs, files in os.walk(selected_directory):
        for file in files:
            if re.match(r'\d{4}-\d{2}-\d{2}_.*$', file, re.IGNORECASE):
                date = datetime.datetime.strptime(file.split('_')[0], '%Y-%m-%d')
                files_with_dates[os.path.join(dirpath, file)] = {'year': date.year, 'month': date.month}
                current_file_iter += 1
                progress = (current_file_iter / total_files) * 100
                progress2_var.set(progress)
                progress2.update()  
            try:
                image = Image.open(os.path.join(dirpath, file))
                exif_data = get_exif_data(image)
                image.close()
                if 'GPSInfo' in exif_data:
                    gps_info = exif_data['GPSInfo']
                    if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                        lat_data = gps_info['GPSLatitude']
                        lon_data = gps_info['GPSLongitude']
                        lat = convert_to_degress(lat_data)
                        lon = convert_to_degress(lon_data)
                        
                        if not math.isnan(lat) and not math.isnan(lon):
                            files_with_gps[os.path.join(dirpath, file)] = (lat, lon)
                            gps_coords.append([lat, lon])    
                        
            except IOError as e:
                pass
            except Exception as e:
                pass

    # Initialize dist_matrix as an empty numpy array
    dist_matrix = np.array([])

    if gps_coords:  # Check if gps_coords is not empty
        gps_coords = np.array(gps_coords)

        # remove any 'inf' or 'NaN' entries
        gps_coords = gps_coords[np.isfinite(gps_coords).all(axis=1)]

        # Calculate the distance matrix in kilometers
        dist_matrix = np.array([[haversine(lat1, lon1, lat2, lon2)
                                 for lat1, lon1 in gps_coords]
                                for lat2, lon2 in gps_coords])

    # Check if dist_matrix is not empty
    if dist_matrix.size > 0:
        # Create a DBSCAN clustering model
        clustering = DBSCAN(eps=radius_in_km, min_samples=1, metric="precomputed")

        # Fit the model with our distance matrix
        clustering.fit(dist_matrix)

        # Assign clusters to files
        for i, ((file, _), cluster) in enumerate(zip(files_with_gps.items(), clustering.labels_)):
            files_with_clusters[file] = {'cluster': cluster, 'longitude': gps_coords[i, 1], 'latitude': gps_coords[i, 0]}


    # Create the final dictionary
    files_final = merge_dicts(files_with_dates, files_with_clusters)
    process_files(files_final)

def run_script1():
    if selected_directory:
        confirmation = show_confirmation_dialog("Figyelmeztetes", f"Atlesznek nevezve a fajlok a {selected_directory} mappaban. Biztos?")
        if confirmation == 'igen':
            run_rename_script()
    else:
        error_label.config(text="Valassz mappat eloszor")

def run_script2():
    if selected_directory:
        confirmation = show_confirmation_dialog("Figyelmeztetes", f"Atlesz mozgatva minden file a {selected_directory} mappaban. Biztos?")
        if confirmation == 'igen':
            radius = radius_entry.get()
            run_process_script(radius)
    else:
        error_label.config(text="Valassz mappat eloszor")

# Define a function to show a custom confirmation dialog
def show_confirmation_dialog(title, message):
    result = tk.StringVar()

    def on_yes():
        result.set("igen")
        dialog.destroy()

    def on_no():
        result.set("nem")
        dialog.destroy()

    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.geometry("400x200")
    dialog.resizable(False, False)
    dialog.configure(bg="pink")

    label = tk.Label(dialog, text=message, font=("Arial", 16), wraplength=380,bg="pink",)
    label.pack(pady=20)

    yes_button = ttk.Button(dialog, text="Igen", command=on_yes)
    yes_button.pack(side=tk.LEFT, padx=20)

    no_button = ttk.Button(dialog, text="Nem", command=on_no)
    no_button.pack(side=tk.RIGHT, padx=20)

    dialog.transient(root)
    dialog.grab_set()

    # Center the dialog window
    root.update_idletasks()
    dialog_width = dialog.winfo_width()
    dialog_height = dialog.winfo_height()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = int((screen_width - dialog_width) / 2)
    y = int((screen_height - dialog_height) / 2)
    dialog.geometry(f"+{x}+{y}")

    root.wait_window(dialog)

    return result.get()



def on_close():
    root.destroy()

current_folder = os.getcwd()
print("Current folder location where program runs:", current_folder)
print("ffmpeg is called in ../build/ffmpeg/bin")

# Set the default radius value
radius = 0.2

# Create the main window
root = tk.Tk()

# Set window title
root.title("Kép rendező kézi készülék")

# Set window size
root.geometry("680x550")

# Center the main window
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 680
window_height = 550
x = int((screen_width - window_width) / 2)
y = int((screen_height - window_height) / 2)
root.geometry(f"+{x}+{y}")

# Create a ttk style
style = ttk.Style(root)
style.configure("TButton", font=("Arial", 20))
style.configure("TProgressbar", thickness=50)

# Create a text label2
text_label = tk.Label(root, text="Megkeresi az osszes kepet es videot, majd megprobalja kiszedni a bennuk levo datumot es atnevezi oket. Amit nem tud, azt megjeloli.", font=("Arial", 12), wraplength=520)
text_label2 = tk.Label(root, text="Beallitasok:", font=("Arial", 20, 'bold'))
text_label3 = tk.Label(root, text="Muveletek:", font=("Arial", 20, 'bold'))
text_label4 = tk.Label(root, text="A megadott mappaban vegigmegy a fajlokon es amennyiben a fajl atlett nevezve az elozo gombbal, akkor fogja es atcsoportositja oket ev -> ho -> helyszin szerint.", font=("Arial", 12), wraplength=520)

# Create file selector button
select_directory_button = ttk.Button(root, text="Valassz mappat", command=select_directory)

# Create buttons
btn1 = ttk.Button(root, text="Atnevez", command=run_script1)
btn2 = ttk.Button(root, text="Elrendez", command=run_script2)

# Create progress bars
progress_var = tk.IntVar()
progress2_var = tk.IntVar()
progress1 = ttk.Progressbar(root, length=300, variable=progress_var, maximum=100)
progress2 = ttk.Progressbar(root, length=300, variable=progress2_var, maximum=100)

# Create label for heading
heading = tk.Label(root, text="Kép rendező kézi készülék", font=("Arial", 24, 'bold', 'underline'))

# Create label for directory path
directory_label = tk.Label(root, text="", font=("Arial", 18))

# Create label and entry for radius
radius_label = tk.Label(root, text="Radiusz (km)", font=("Arial", 18))
radius_entry_var = tk.StringVar(value=str(radius))  # Use the default radius value
radius_entry = ttk.Entry(root, textvariable=radius_entry_var, font=("Arial", 18))

# Create error label
error_label = tk.Label(root, text="", fg="red", font=("Arial", 16))

# Create progress labels
progress_label1 = tk.Label(root, text="", font=("Arial", 16))
progress_label2 = tk.Label(root, text="", font=("Arial", 16))

# Place the elements using absolute positioning
heading.place(x=130, y=20)

btn1.place(x=55, y=280, width=200, height=50)
progress1.place(x=280, y=280, width=300, height=50)
progress_label1.place(x=585, y=290)

btn2.place(x=55, y=400, width=200, height=50)
progress2.place(x=280, y=400, width=300, height=50)
progress_label2.place(x=585, y=410)

radius_label.place(x=55, y=180)
radius_entry.place(x=210, y=181, width=100)
error_label.place(x=55, y=220)

text_label.place(x=55, y=330)
text_label2.place(x=55, y=90)
text_label3.place(x=55, y=240)
text_label4.place(x=55, y=450)
select_directory_button.place(x=55, y=130)
directory_label.place(x=310, y=135)

# Add a ScrolledText widget for the log panel
#log_panel = scrolledtext.ScrolledText(root, wrap = tk.WORD, width = 70, height = 10, state='disabled')  # width and height as per your needs
#log_panel.place(x=55, y=550)  # place the log panel where you want

# Start the GUI event loop
root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
