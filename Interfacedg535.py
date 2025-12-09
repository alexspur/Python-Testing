import pyvisa
import pyserial
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from loguru import logger
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import ttkbootstrap as ttkb
from threading import Thread


def gpib_write(cmd):
    """Send a GPIB command through Prologix."""
    global dg535
    if not dg535:
        return
    dg535.write(f"{cmd}\n".encode())

def gpib_query(cmd):
    """Send a command and read back the response."""
    global dg535
    if not dg535:
        return ""
    dg535.write(f"{cmd}\n".encode())
    dg535.write(b"++read eoi\n")
    return dg535.readline().decode(errors="ignore").strip()

def show_help_delay_channels():
    messagebox.showinfo("Help - Delay Channels", "This section allows you to set the delay for different channels (A, B, C, D).")


def show_help_plot():
    help_message = (
                   "This section displays two plot:\n"
                   "1) Shows the delays of the 4 channels relative to a common internal time reference T0\n"
                   "2) Shows the duration of the AB and CD channel pulses\n")
    messagebox.showinfo("Help - Plot", help_message)


def show_help_set_frequency():
    messagebox.showinfo("Help - Set Frequency", "This section allows you to set the frequency in Hz, please specify a positive numerical value in Hz. This option won't affect the settled delays .")

def show_help_start():
    help_message = (
                        "This section starts the pulse generator at the given internal frequency and at the following default delays for the channel:\n\n"
                        "Channel A: 0 ns\n"                  
                        "Channel B: 5 microsecondss\n"
                        "Channel C: 250 microseconds\n"
                        "Channel D: 251 microseconds\n"
                        "If no frequency is specified, then a default value of 10 Hz is settled.\n"  
                        "Please fine tune the delays in case those values must be changed.\n"    
                        "Do not attempt to increase the frequency over 100 Hz, bad things might happen (i will not allow you... )"
                            )
    messagebox.showinfo("Help - Start and Stop Section" , help_message
                            )

    
    




def update_connection_status():
    """
    Funzione per aggiornare lo stato della connessione.
    """
    global dg535
    global connection_status_label
    if dg535:
        connection_status_label.config(text="Connected", bg="green", fg="white")
    else:
        connection_status_label.config(text="Not Connected", bg="red", fg="white")



# def update_mode_status():
#     """
#     Funzione per aggiornare stato 
#     """
#     global dg535
#     global trigger_label
#     if not dg535:
#         trigger_label.config(text="Trigger Status: Not available", bg="black", fg="white")
#         return -1

#     status = dg535.query("TM")
#     if status[0] == "0": #Check
#         trigger_label.config(text = "Trigger Status: Internal Trigger On", bg = "green", fg = "white")
#     else:
#         trigger_label.config(text = "Trigger Status: Internal Trigger Off", bg = "red", fg = "white")
def update_mode_status():
    global trigger_label
    status = gpib_query("TM")
    if not status:
        trigger_label.config(text="Trigger Status: Not available", bg="black", fg="white")
        return
    if status[0] == "0":
        trigger_label.config(text="Trigger Status: Internal Trigger On", bg="green", fg="white")
    else:
        trigger_label.config(text="Trigger Status: Internal Trigger Off", bg="red", fg="white")        
    
def check_connection():
    global dg535
    global rm
    devices = rm.list_resources()
    # Check if any GPIB devices are connected
    gpib_devices = [device for device in devices if "GPIB" in device]
    if not gpib_devices:
        messagebox.showwarning("Warning", "There are no GPIB devices connected! Please check the connection again!")
    try:
        dg535.query("TM")
    except:
        messagebox.showwarning("Error","Connection could have been lost with the device: please check the physical connection. Use the third party driver to re-establish connnection.")
        dg535 = None
        update_connection_status()
        update_mode_status()
    
    
def loop_check():
    global dg535
    global rm
    
    check_connection()
    window.after(10000, loop_check())

def list_devices():
    devices = pyvisa.ResourceManager().list_resources()
    messagebox.showinfo("Devices", f"Available devices: {devices}")
        

# def connect_to_dg535():
#     """
#     This function connects the computer to the dg535 device, 
#     in case there is more than one device connected please specify the right item from the list that will be returned in this case
#     """
#     # Initialize VISA resource manager
#     global rm
#     global dg535

#     rm = pyvisa.ResourceManager()
#     # List all available devices
#     devices = rm.list_resources()
#     messagebox.showinfo("Devices", f"Available devices: {devices}")
#     # Check if any GPIB devices are connected
#     gpib_devices = [device for device in devices if "GPIB" in device]
#     if not gpib_devices:
#         messagebox.showwarning("Warning", "There are no GPIB devices connected!")
#         return None  # Return None to indicate connection failure
#     dg535_address = gpib_devices[0]        
#     # Connect to the DG535
#     try:
#         dg535 = rm.open_resource(dg535_address)
#     except:
#         messagebox.showwarning("Error","Connection could have been lost with the device: please check the physical connection. Use the third party driver to re-establish connnection.")
#         dg535 = None
#     #update_values_fasullo(dg535)
#     #update_values(dg535)
#     #update_mode_status()
#     return dg535
import serial
import serial.tools.list_ports

def connect_to_dg535(port=None, baud=115200, gpib_addr=15):
    """
    Connect to DG535 through Prologix GPIB-USB adapter on a COM port.
    Returns a serial.Serial object.
    """
    global dg535

    # Detect available COM ports
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        messagebox.showwarning("Warning", "No COM ports found! Please connect the Prologix adapter.")
        return None

    if port is None:
        # If not specified, use the first one
        port = ports[0]
        messagebox.showinfo("Port Detected", f"Using port: {port}")

    try:
        # Open serial connection
        dg535 = serial.Serial(port, baudrate=baud, timeout=1)
        dg535.write(b"++mode 1\n")        # Controller mode
        dg535.write(b"++auto 0\n")        # Disable read-after-write
        dg535.write(b"++eoi 1\n")         # Assert EOI on last byte
        dg535.write(b"++eos 3\n")         # No CR/LF appended
        dg535.write(f"++addr {gpib_addr}\n".encode())  # Set DG535 GPIB address
        dg535.flush()
        messagebox.showinfo("Connected", f"Connected to DG535 on {port} (GPIB {gpib_addr})")
        return dg535
    except Exception as e:
        messagebox.showerror("Error", f"Failed to connect on {port}\n{e}")
        dg535 = None
        return None




def update_values(dg535):
    """
    Function to update internal tigger frequency and C Channel delay values.
    """
    check_connection()
    if not dg535:
        return -1
    f = dg535.query("TR 0")
    f = float(f[:len(f)-2])
    
    t_A = dg535.query("DT 2")
    t_A = float(t_A[2:len(t_A)-2])
    t_B = dg535.query("DT 3")
    t_B = float(t_B[2:len(t_B)-2])

    t_C = dg535.query("DT 5")
    t_C = float(t_C[2:len(t_C)-2])

    t_D = dg535.query("DT 6")
    t_D = float(t_D[2:len(t_D)-2])

    
    global frequency_var
    global delay_var_A
    global delay_var_B
    global delay_var_C
    global delay_var_D
    global current_delay_var_A
    global current_delay_var_B
    global current_delay_var_C
    global current_delay_var_D
    list_delay_var = [delay_var_A,delay_var_B,delay_var_C,delay_var_D]
    list_current_delays = [current_delay_var_A,current_delay_var_B,current_delay_var_C,current_delay_var_D]
    list_var2 =  [t_A, t_B, t_C, t_D]
    channels = ["A", "B", "C", "D"]
    
    for i, delay in enumerate(list_delay_var):
        delay.set(f"Channel {channels[i]} delay set to : {list_var2[i]} [s]")
        list_current_delays[i].set(f'{list_var2[i]}')
        
    frequency_var.set(f"Internal Trigger frequency set to: {f} [Hz]")
    update_graph()



def retry_connection():
    """
    Function to retry connection to the DG535 device.
    """
    connection_status_label.config(text="Checking connection...", bg="gray", fg="white")
    global dg535
    dg535 = connect_to_dg535()
    if dg535:
        messagebox.showinfo("Connection", "Successfully connected to the DG535!")
        
    else:
        messagebox.showwarning("Connection Failed", "Retry connection failed. Please check the device and try again.")
    update_connection_status()
    update_mode_status()
    update_graph()


def stop(dg535):
    
    """
    @params dg535 : the device 
    This function switches the device from internal trigger to single shot mode, hence stopping the pulse generator.
    """ 
    # set trigger to single shot, this stops execution.
    dg535.write('TM 2')
    update_mode_status()


def change_frequency(dg535, f):
    
    """
    @params dg535 : the device
    @params f : the new frequency in Hz
    This function changes the internal trigger frequency of the device. 
    """
    check_connection()
    messagebox.showwarning("Warning", f"The frequency of the internal trigger is being changed to {f} Hz, you may need to change the delays to the channels if needed. ")
    commandstring = f'TR 0,{f}'
    dg535.write(commandstring)
    update_values(dg535)


def start(dg535, f):
    """
    @params dg535 : the device
    @params f : the frequency to set, to be specified in Hz
    """
    messagebox.showinfo("Starting the pulse generator", "Attempting to start the pulse generator...\n channel A delay channel is set to default 100 [ns], channel B delay is set to  default of 200 [ns]\n channel C delay is set to default of 250 microseconds \n channel D delay is set to default of 251 microseconds.")

    # delay A from T0 of 100 ns
    dg535.write('DT 2,1,0.0')
    # delay B from A 100 ns
    dg535.write('DT 3,1,5E-6')
    # delay C 250 microseconds compared to T0
    dg535.write('DT 5,1,200E-6')
    #delay D 251 microseconds compared to T0
    dg535.write('DT 6,1,251E-6')
    # change frequency and set trigger to internal
    change_frequency(dg535, f)
    dg535.write('TM 0')
    update_values(dg535)
    update_mode_status()
    messagebox.showwarning("Warning","The delays have been settled to a common point of reference T0 in time, the given default values have been settled, if needed one can change those values manually in the delay section.")







def check_delay(t, Channel):
    global current_delay_var_A
    global current_delay_var_B
    global current_delay_var_C
    global current_delay_var_D

    
    dict_var = {2:float(current_delay_var_A.get()),
                3:float(current_delay_var_B.get()),
                5:float(current_delay_var_C.get()),
                6:float(current_delay_var_D.get())
           }
           
    dict_check_backward = {3:2,
                           5:3,
                           6:5
                           }
    dict_name = {2:"A",
                 3:"B",
                 5:"C",
                 6:"D"
                }
    dict_check_forward ={2:3,
                         3:5,
                         5:6
                        
                        }
    if (Channel != 2):
        if  t < dict_var[dict_check_backward[Channel]]:
            messagebox.showwarning("Warning", f"Channel {dict_name[Channel]} delay is less than channel {dict_name[dict_check_backward[Channel]]} delay.\n Remember that the delays are ordered in A->B->C->D")
            return -1
    if (Channel != 6):
        if  t > dict_var[dict_check_forward[Channel]]:
            messagebox.showwarning("Warning", f"Channel {dict_name[Channel]} delay is more than channel {dict_name[dict_check_forward[Channel]]} delay.\n Remember that the delays are ordered in A->B->C->D")
            return -1


def delay(dg535,Channel,  t):
    """
    This function delays the current channel compared to a common internal reference T0
    @params dg535 : the device
    @params Channel. the channel which is being delayed
    @params t : the delay, to be specified in seconds.
    """
    flag = check_delay(t, Channel)
    if flag == -1:
        return -1
    command = f'DT {Channel},1,{t}'
    
    dg535.write(command)
    update_values(dg535)
    update_graph()







def show_help():
    """
    Function to display the help window.
    """
    help_message = (
        "Pulse Generator Interface Help\n\n"

        "1. Start: Enter an initial frequency and press Start to activate the pulse generator, default is 2kHz.\n"
        "2. Stop: Press Stop to halt the pulse generator and interrupt the internal trigger.\n"
        "3. Set Internal Frequency: Enter the desired frequency and press the button to change the internal trigger frequency.\n"
        "4. Set Delay: Enter a delay value in seconds and press Set Delay to apply the delay to Channel C.\n"
        "5. Retry Connection: Press Retry Connection to attempt reconnecting to the DG535 device.\n"
        "6. Help: Displays this help window.\n "
        "Care: this code works if only one GPIB device is connected."
    )
    messagebox.showinfo("Help", help_message)




# set internal trigger frequency function
def set_trigger_frequency():
    """
        Function that activates when the Set Frequency button is pressed
    """
    check_connection()

    if not dg535:
        messagebox.showwarning("Error", "There is no GPIB device, please check the connection.")
        return -1
    
    if entry_trigger.get():
        try:
            frequency = float(entry_trigger.get())
        except:
            messagebox.showwarning("Error", "Please insert a valid value")
            return -1
        if frequency <= 0:
            messagebox.showwarning("Error", "Please insert a non-negative value")
            return -1
        if frequency >100:
            messagebox.showerror("Bruh", " Y burn transstor_? <100 Hz pls")
            return -1
        if frequency:
            change_frequency(dg535, frequency)
            update_graph()
            messagebox.showinfo("Impostato", f"Internal Trigger frequency set to: {frequency} Hz")
        else:
            messagebox.showwarning("Warning", "Please insert a valid frequency!")
            return -1
    
        

# start function
def start_action():
    """
    Function that activates when the start button is pressed
    """
    check_connection()

    if not dg535:
        messagebox.showwarning("Error", "There is no GPIB device, please check the connection.")
        return -1

        
    if entry_start.get():
        try:
            initial_frequency = float(entry_start.get())
        except:
            messagebox.showwarning("Error", "Please insert a valid value")
            return -1
        start(dg535, initial_frequency)
        messagebox.showinfo("Starting", f"Internal trigger frequency set to: {initial_frequency} Hz")
    else:
        start(dg535, 10)
        messagebox.showinfo("Starting", f"Internal trigger frequency set to a default value of 10 Hz since no value was specified")

# stop function
def stop_action():
    """
    Function that activates when the stop button is pressed
    """
    check_connection()

    if not dg535:
        messagebox.showwarning("Error", "There is no GPIB device, please check the connection.")
        return -1
    stop(dg535)
    messagebox.showwarning("Stop", "The pulse generator has been switched to single shot mode: continuous pulse generation with internal trigger frequency has been stopped!")

# set delay functon
def set_delay(Channel, t):
    """
    Function that activates when the set delay button is pressed
    """
    check_connection()
    if not dg535:
        messagebox.showwarning("Error", "There is no GPIB device, please check the connection.")
        return -1   
    global current_delay_var_A
    global current_delay_var_B

    global current_delay_var_C
    global current_delay_var_D

    dict_var = {2:float(current_delay_var_A.get()),
                3:float(current_delay_var_B.get()),

                5:float(current_delay_var_C.get()),
                6:float(current_delay_var_D.get()) 
           }
           
    dict_check_backward = {3:2,
                           5:3,
                           6:5
                           }
    dict_name = {2:"A",
                 3:"B",
                 5:"C",
                 6:"D"
                }
    dict_check_forward ={2:3,
                         3:5,
                         5:6
                        }
    
    if not dg535:
        messagebox.showwarning("Error", "There is no GPIB device, please check the connection.")
        return -1
    
    if t:
        try:
            t = float(t)
        except:
            messagebox.showwarning("Error", "Please insert a valid value")
            return -1
        if  t < 0:
            messagebox.showwarning("Error", "Please insert a non-negative value")
            return -1
        else:
            if (Channel!=2):
                if  t < dict_var[dict_check_backward[Channel]]:
                    messagebox.showwarning("Warning", f"Channel {dict_name[Channel]} delay is less than channel {dict_name[dict_check_backward[Channel]]} delay.\n Remember that the delays must be ordered such that A<B<C<D")
                    return -1
            if (Channel !=6):
                if  t > dict_var[dict_check_forward[Channel]]:
                    messagebox.showwarning("Warning", f"Channel {dict_name[Channel]} delay is more than channel {dict_name[dict_check_forward[Channel]]} delay.\n Remember that the delays must be ordered such that A<B<C<D")
                    return -1
            delay(dg535,Channel,t)
            messagebox.showinfo("Delay settled", f"Delay settled to: {t} seconds for channel {dict_name[Channel]}")
    else:
        messagebox.showwarning("Error", "No value was inserted")






def update_graph(scale_type="linear"):
    
    check_connection()
    if not dg535:
        return -1
    
    delays = {
        'T0 time reference' : 0, 
        'Channel A': float(current_delay_var_A.get()) or 0,
        'Channel B': float(current_delay_var_B.get()) or 0,
        'Channel C': float(current_delay_var_C.get()) or 0,
        'Channel D': float(current_delay_var_D.get()) or 0,

    }
    
    
    
    
    
    
    # Prepare time values for plotting
    channels = list(delays.keys())
    time_delays = list(delays.values())

    # Create the plot
    fig, ax = plt.subplots(2 ,1, figsize=(6, 3), layout = "constrained", sharex = True)  # Adjust the figure size
    colors = ['red', 'blue', 'green', 'orange', 'purple']


    ax[0].scatter(time_delays, channels, color=colors, edgecolor='black', s=100)  # s is the size of points
    ax[0].set_title('Channels\' starting point')
    ax[0].set_xlabel('Time [s]', fontsize=10)    
    # Set scale type (linear or logarithmic)
    ax[0].set_xscale(scale_type)
    ax[0].set_facecolor("#cccccc")

    fig.patch.set_facecolor("#cccccc")
    # Add gridlines
    ax[0].grid(True, which='both', linestyle='--', linewidth=0.5)
    # Add ticks and labels
    ax[0].xaxis.set_major_formatter(plt.ScalarFormatter())
    ax[0].xaxis.set_minor_formatter(plt.NullFormatter())
    
    
    AB_pulse_start = delays['Channel A']
    AB_pulse_end = delays['Channel B']
    CD_pulse_start = delays['Channel C']
    CD_pulse_end = delays['Channel D'] #check whether this is true
    pulse_channels = ['Channel AB', 'Channel CD']

    end_pos = [AB_pulse_end-AB_pulse_start, CD_pulse_end-CD_pulse_start]
    start_pos = [AB_pulse_start, CD_pulse_start]
    
    
    colors_pulses = ['cyan', 'purple']
    # Horizontal bar plot for the second subplot
    bars = ax[1].barh(pulse_channels, end_pos, color=colors_pulses, edgecolor='black', left=start_pos)
    ax[1].set_xlabel('Time (s)')
    ax[1].set_ylabel('Channels')
    ax[1].set_facecolor("#cccccc")
    ax[1].set_title('Channel AB and CD pulses duration')
    ax[1].set_xscale(scale_type)
    ax[1].grid(True, which='both', linestyle='--', linewidth=0.5)
    

    
    
    
    
    
    # Clear the old canvas and redraw the new one
    for widget in frame_plot.winfo_children():
        widget.destroy()

    canvas = FigureCanvasTkAgg(fig, master=frame_plot)

    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=False)
    canvas.draw()







# Main window
window = tk.Tk()
window.title("Interface to pilot Pulse generator DG535")

# Set width and height of window to half the screen 
screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()
window.geometry(f"{screen_width}x{screen_height}") 






# Create a menu bar
menu_bar = tk.Menu(window)
window.config(menu=menu_bar)

# Create a Help menu
help_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Menu&Help", menu=help_menu)
help_menu.add_command(label="Help", command=show_help)
help_menu.add_command(label = "Devices", command = list_devices)


# Background color and other options
section_bg = "#cccccc"  
title_font = ('Serif', 12, 'bold')




# First section: retry connection and also ifo
frame_retry = tk.LabelFrame(window, text = "CONNECTION SECTION", padx=20, pady=20, bg=section_bg, font=title_font, borderwidth=2, relief="groove")
frame_retry.pack(anchor='c', padx=20, pady=20)

connection_status_label = tk.Label(frame_retry, text="Checking connection...", bg="gray", fg="white", width=30, height=2)
connection_status_label.pack(side = tk.RIGHT, padx = 20)

button_retry = tk.Button(frame_retry, text="Retry Connection",bg = "blue", fg = 'white', command=retry_connection)
button_retry.pack()





# Second section: start and stop 
frame_start_stop = tk.LabelFrame(window, text="CONTROL SECTION", padx=20, pady=20, bg=section_bg,font=title_font, borderwidth=2, relief="groove")
frame_start_stop.pack(anchor='w', padx=20, pady=20, fill="both", expand="no")

# Start button
frame_start = tk.Frame(frame_start_stop, bg=section_bg)
frame_start.pack(anchor='w', pady=10)


#help button for start section
button_help_start = tk.Button(frame_start, text="?", command=show_help_start, width=2)
button_help_start.pack(side = tk.RIGHT, padx=5, pady=5)





label_start = tk.Label(frame_start, text="Initial internal trigger frequency", bg=section_bg)
label_start.pack(side=tk.LEFT, padx=5)

entry_start = tk.Entry(frame_start, width=10)
entry_start.pack(side=tk.LEFT, padx=5)

label_hz_start = tk.Label(frame_start, text="[Hz]", bg=section_bg)
label_hz_start.pack(side=tk.LEFT)

button_start = tk.Button(frame_start, text="Start", command=start_action, bg="green", fg = 'white')
button_start.pack(side=tk.LEFT, padx=10)

# Stop button
button_stop = tk.Button(frame_start, text="Stop", command=stop_action, bg="red", fg="white")
button_stop.pack(side=tk.LEFT, pady=10)

# Trigger window: tells if it is connected or less
trigger_label = tk.Label(frame_start, text="Checking trigger mode...", bg="gray", fg="white", width=30, height=2)
trigger_label.pack(side = tk.RIGHT, padx = 20)





# Set internal trigger frequency section
frame_set_internal = tk.LabelFrame(window, text="SET INTERNAL TRIGGER FREQUENCY", padx=20, pady=20, bg=section_bg,font=title_font, borderwidth=2, relief="groove")
frame_set_internal.pack(anchor='w', padx=20, pady=20, fill="both", expand="no")
#help button for frequency section
button_help_freq = tk.Button(frame_set_internal, text="?", command=show_help_set_frequency, width=2)
button_help_freq.pack(side=tk.RIGHT, padx=5, pady=5)


label_trigger = tk.Label(frame_set_internal, text="Change internal trigger frequency", bg=section_bg)
label_trigger.pack(side=tk.LEFT, padx=5)

entry_trigger = tk.Entry(frame_set_internal, width=10)
entry_trigger.pack(side=tk.LEFT, padx=5)

label_hz_trigger = tk.Label(frame_set_internal, text="[Hz]", bg=section_bg)
label_hz_trigger.pack(side=tk.LEFT)

button_set = tk.Button(frame_set_internal, text="Set", command=set_trigger_frequency)
button_set.pack(side=tk.LEFT, padx=10)





# Variables to store frequency and delay
internal_frequency = tk.StringVar(value="0")
    
# Create labels for frequency and delay in the value window
frequency_var = tk.StringVar(value="Internal Frequency: Unknown [Hz]")


label_frequency = tk.Label(frame_set_internal, textvariable=frequency_var, bg=section_bg, font=('Helvetica', 10))
label_frequency.pack(pady=10)











# Frame for DELAY CHANNELS section
frame_delay = tk.LabelFrame(window, text="DELAY CHANNELS", padx=20, pady=20, bg=section_bg, font=title_font, borderwidth=2, relief="groove")
frame_delay.pack(pady=10, fill="x", padx=20, anchor='w', expand="no")


# Pulsante Help per la sezione "Delay Channels"
button_help_delay = tk.Button(frame_delay, text="?", command=show_help_delay_channels, width=2)
button_help_delay.grid(row=0, column=16, padx=5, pady=5 , sticky = 'w')





# Row 0: Delay Channel A
label_delay_Channel_A = tk.Label(frame_delay, text="Delay Channel A", bg=section_bg)
label_delay_Channel_A.grid(row=0, column=0, padx=5, pady=5, sticky="w")

entry_delay_Channel_A = tk.Entry(frame_delay, width=10)
entry_delay_Channel_A.grid(row=0, column=1, padx=5, pady=5)

label_seconds_Channel_A = tk.Label(frame_delay, text="[s]", bg=section_bg)
label_seconds_Channel_A.grid(row=0, column=2, padx=5, pady=5)

button_set_delay_Channel_A = tk.Button(frame_delay, text="Set", command=lambda: set_delay(2, entry_delay_Channel_A.get()))
button_set_delay_Channel_A.grid(row=0, column=3, padx=10, pady=5)

current_delay_var_A = tk.StringVar()
delay_var_A = tk.StringVar(value="A Channel Delay: Unknown [s]")
label_delay_A = tk.Label(frame_delay, textvariable=delay_var_A, bg=section_bg, font=('Helvetica', 10))
label_delay_A.grid(row=0, column = 4, padx = 10, pady = 5)



# Row 1: Delay Channel B
label_delay_Channel_B = tk.Label(frame_delay, text="Delay Channel B", bg=section_bg)
label_delay_Channel_B.grid(row=1, column=0, padx=5, pady=5, sticky="w")

entry_delay_Channel_B = tk.Entry(frame_delay, width=10)
entry_delay_Channel_B.grid(row=1, column=1, padx=5, pady=5)

label_seconds_Channel_B = tk.Label(frame_delay, text="[s]", bg=section_bg)
label_seconds_Channel_B.grid(row=1, column=2, padx=5, pady=5)

button_set_delay_Channel_B = tk.Button(frame_delay, text="Set", command=lambda: set_delay(3, entry_delay_Channel_B.get()))
button_set_delay_Channel_B.grid(row=1, column=3, padx=10, pady=5)

current_delay_var_B = tk.StringVar()
delay_var_B = tk.StringVar(value="B Channel Delay: Unknown [s]")
label_delay_B = tk.Label(frame_delay, textvariable=delay_var_B, bg=section_bg, font=('Helvetica', 10))
label_delay_B.grid(row=1, column = 4, padx = 10, pady = 5)



frame_delay.grid_columnconfigure(5, minsize=500)


# Row 2: Delay Channel C
label_delay_Channel_C = tk.Label(frame_delay, text="Delay Channel C", bg=section_bg)
label_delay_Channel_C.grid(row=0, column=7, padx=5, pady=5, sticky="e")

entry_delay_Channel_C = tk.Entry(frame_delay, width=10)
entry_delay_Channel_C.grid(row=0, column=8, padx=5, pady=5, sticky="e")

label_seconds_Channel_C = tk.Label(frame_delay, text="[s]", bg=section_bg)
label_seconds_Channel_C.grid(row=0, column=9, padx=5, pady=5, sticky="e")

button_set_delay_Channel_C = tk.Button(frame_delay, text="Set", command=lambda: set_delay(5, entry_delay_Channel_C.get()))
button_set_delay_Channel_C.grid(row=0, column=10, padx=10, pady=5, sticky="e")

# Row 3: Delay Channel D
label_delay_Channel_D = tk.Label(frame_delay, text="Delay Channel D", bg=section_bg)
label_delay_Channel_D.grid(row=1, column=7, padx=5, pady=5, sticky="e")

entry_delay_Channel_D = tk.Entry(frame_delay, width=10)
entry_delay_Channel_D.grid(row=1, column=8, padx=5, pady=5, sticky="e")

label_seconds_Channel_D = tk.Label(frame_delay, text="[s]", bg=section_bg)
label_seconds_Channel_D.grid(row=1, column=9, padx=5, pady=5, sticky="e")

button_set_delay_Channel_D = tk.Button(frame_delay, text="Set", command=lambda: set_delay(6, entry_delay_Channel_D.get()))
button_set_delay_Channel_D.grid(row=1, column=10, padx=10, pady=5, sticky="e")




current_delay_var_C = tk.StringVar()
delay_var_C = tk.StringVar(value="C Channel Delay: Unknown [s]")
label_delay_C = tk.Label(frame_delay, textvariable=delay_var_C, bg=section_bg, font=('Helvetica', 10))
label_delay_C.grid(row=0, column = 11, padx = 10, pady = 5, sticky="e")


current_delay_var_D = tk.StringVar()
delay_var_D = tk.StringVar(value="D Channel Delay: Unknown [s]")
label_delay_D = tk.Label(frame_delay, textvariable=delay_var_D, bg=section_bg, font=('Helvetica', 10))
label_delay_D.grid(row=1, column = 11, padx = 10, pady = 5, sticky="e")



# Frame to hold the plot
frame_plot = tk.Frame(window)
frame_plot.pack(fill=tk.BOTH, expand="yes", pady = 10, padx = 10)




# Buttons for updating the graph
frame_buttons = tk.Frame(window, padx = 10, pady = 10)
frame_buttons.pack(side=tk.TOP, pady=10, anchor = 'w', expand = 'yes')




# Dropdown for scale selection
scale_type = tk.StringVar(value="linear")

def on_scale_change(event=None):
    update_graph(scale_type.get())

scale_dropdown = ttk.Combobox(frame_buttons, textvariable=scale_type, values=["linear", "log"], state="readonly")
scale_dropdown.grid(row=0, column=0, padx=5)
scale_dropdown.bind("<<ComboboxSelected>>", on_scale_change)

# Button to update graph
button_update_graph = tk.Button(frame_buttons, text="Update Graph", command=lambda: update_graph(scale_type.get()))
button_update_graph.grid(row=0, column=1, padx=5)

#help button for start section
button_help_plot = tk.Button(frame_buttons, text="?", command=show_help_plot, width=2)
button_help_plot.grid(row=0, column=2, padx=5, pady=5 , sticky = 'w')



# First connection to device.
dg535 = connect_to_dg535()
update_connection_status()
update_mode_status()
update_values(dg535)

# Initial plot
update_graph()

"""
thread1 = Thread(target =loop_check())

# Interface loop
thread2 = Thread(target = window.mainloop())
thread1.start()
thread2.start()
thread1.join()
"""
window.mainloop()
