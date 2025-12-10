# # # gui/scope_plot_window.py
# # from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
# # import pyqtgraph as pg


# # class ScopePlotWindow(QWidget):
# #     def __init__(self, parent=None):
# #         super().__init__()
# #         self.parent = parent

# #         layout = QVBoxLayout()
# #         self.setLayout(layout)

# #         # Existing plot widgets
# #         self.plot1 = pg.PlotWidget(background='w')
# #         self.plot2 = pg.PlotWidget(background='w')
# #         self.plot3 = pg.PlotWidget(background='w')

# #         layout.addWidget(self.plot1)
# #         layout.addWidget(self.plot2)
# #         layout.addWidget(self.plot3)

# #         # ⭐ Add CLEAR button
# #         self.btn_clear = QPushButton("Clear All Plots")
# #         layout.addWidget(self.btn_clear)

# #         # Connect it
# #         self.btn_clear.clicked.connect(self.clear_plots)

# #         # --------------------------------------------------------
# #         #   BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
# #         # --------------------------------------------------------
# #         btn_row = QHBoxLayout()

# #         # R1 buttons
# #         self.btn_r1_single = QPushButton("R1 SINGLE")
# #         self.btn_r1_capture = QPushButton("Capture R1")

# #         # R2 buttons
# #         self.btn_r2_single = QPushButton("R2 SINGLE")
# #         self.btn_r2_capture = QPushButton("Capture R2")

# #         # R3 buttons
# #         self.btn_r3_single = QPushButton("R3 SINGLE")
# #         self.btn_r3_capture = QPushButton("Capture R3")

# #         # Add all to layout
# #         btn_row.addWidget(self.btn_r1_single)
# #         btn_row.addWidget(self.btn_r1_capture)
# #         btn_row.addWidget(self.btn_r2_single)
# #         btn_row.addWidget(self.btn_r2_capture)
# #         btn_row.addWidget(self.btn_r3_single)
# #         btn_row.addWidget(self.btn_r3_capture)

# #         layout.addLayout(btn_row)

# #         # Connect signals to handlers
# #         self.btn_r1_single.clicked.connect(self.on_r1_single)
# #         self.btn_r1_capture.clicked.connect(self.on_r1_capture)
# #         self.btn_r2_single.clicked.connect(self.on_r2_single)
# #         self.btn_r2_capture.clicked.connect(self.on_r2_capture)
# #         self.btn_r3_single.clicked.connect(self.on_r3_single)
# #         self.btn_r3_capture.clicked.connect(self.on_r3_capture)

# #     def clear_plots(self):
# #         self.plot1.clear()
# #         self.plot2.clear()
# #         self.plot3.clear()

# #     # ------------------------------------------------------------
# #     # R1 HANDLERS
# #     # ------------------------------------------------------------
# #     def on_r1_single(self):
# #         if hasattr(self.parent, "rigol1"):
# #             try:
# #                 self.parent.rigol1.inst.write(":STOP")
# #                 self.parent.rigol1.inst.write(":SINGLE")
# #             except Exception as e:
# #                 print("R1 SINGLE error:", e)

# #     def on_r1_capture(self):
# #         if hasattr(self.parent, "on_capture_r1"):
# #             self.parent.on_capture_r1()

# #     # ------------------------------------------------------------
# #     # R2 HANDLERS
# #     # ------------------------------------------------------------
# #     def on_r2_single(self):
# #         if hasattr(self.parent, "rigol2"):
# #             try:
# #                 self.parent.rigol2.inst.write(":STOP")
# #                 self.parent.rigol2.inst.write(":SINGLE")
# #             except Exception as e:
# #                 print("R2 SINGLE error:", e)

# #     def on_r2_capture(self):
# #         if hasattr(self.parent, "on_capture_r2"):
# #             self.parent.on_capture_r2()

# #     # ------------------------------------------------------------
# #     # R3 HANDLERS
# #     # ------------------------------------------------------------
# #     def on_r3_single(self):
# #         if hasattr(self.parent, "rigol3"):
# #             try:
# #                 self.parent.rigol3.inst.write(":STOP")
# #                 self.parent.rigol3.inst.write(":SINGLE")
# #             except Exception as e:
# #                 print("R3 SINGLE error:", e)

# #     def on_r3_capture(self):
# #         if hasattr(self.parent, "on_capture_r3"):
# #             self.parent.on_capture_r3()


# # gui/scope_plot_window.py
# from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
# from PyQt6.QtGui import QFont
# import pyqtgraph as pg
# from pyqtgraph import ViewBox, PlotCurveItem


# class ScopePlotWindow(QWidget):
#     def __init__(self, parent=None):
#         super().__init__()
#         self.parent = parent

#         layout = QVBoxLayout()
#         self.setLayout(layout)

#         # --------------------------------------------------------
#         # PLOT 1 (Rigol #1) — dual-axis
#         # --------------------------------------------------------
#         # self.plot1 = pg.PlotWidget(background='w')
#         # layout.addWidget(self.plot1)
#         # self._setup_dual_axis(self.plot1)
#         # self.r1_ch1 = self.plot1_ch1
#         # self.r1_ch2 = self.plot1_ch2

#         # # --------------------------------------------------------
#         # # PLOT 2 (Rigol #2)
#         # # --------------------------------------------------------
#         # self.plot2 = pg.PlotWidget(background='w')
#         # layout.addWidget(self.plot2)
#         # self._setup_dual_axis(self.plot2)
#         # self.r2_ch1 = self.plot2_ch1
#         # self.r2_ch2 = self.plot2_ch2

#         # # --------------------------------------------------------
#         # # PLOT 3 (Rigol #3)
#         # # --------------------------------------------------------
#         # self.plot3 = pg.PlotWidget(background='w')
#         # layout.addWidget(self.plot3)
#         # self._setup_dual_axis(self.plot3)
#         # self.r3_ch1 = self.plot3_ch1
#         # self.r3_ch2 = self.plot3_ch2
#         # PLOT 1 (Rigol #1)
#         self.plot1 = pg.PlotWidget(background='w')
#         self.plot1.getPlotItem().setContentsMargins(10, 10, 20, 10)
#         layout.addWidget(self.plot1)
#         self.r1_ch1, self.r1_ch2 = self._setup_dual_axis(self.plot1)

#         # PLOT 2 (Rigol #2)
#         self.plot2 = pg.PlotWidget(background='w')
#         self.plot2.getPlotItem().setContentsMargins(10, 10, 20, 10)
#         layout.addWidget(self.plot2)
#         self.r2_ch1, self.r2_ch2 = self._setup_dual_axis(self.plot2)

#         # PLOT 3 (Rigol #3)
#         self.plot3 = pg.PlotWidget(background='w')
#         self.plot3.getPlotItem().setContentsMargins(10, 10, 20, 10)
#         layout.addWidget(self.plot3)
#         self.r3_ch1, self.r3_ch2 = self._setup_dual_axis(self.plot3)

#         # Apply Times New Roman bold font to all plots
#         self._apply_font_styling()


#         # --------------------------------------------------------
#         # CLEAR button
#         # --------------------------------------------------------
#         self.btn_clear = QPushButton("Clear All Plots")
#         layout.addWidget(self.btn_clear)
#         self.btn_clear.clicked.connect(self.clear_plots)

#         # --------------------------------------------------------
#         # BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
#         # --------------------------------------------------------
#         btn_row = QHBoxLayout()

#         self.btn_r1_single = QPushButton("R1 SINGLE")
#         self.btn_r1_capture = QPushButton("Capture R1")

#         self.btn_r2_single = QPushButton("R2 SINGLE")
#         self.btn_r2_capture = QPushButton("Capture R2")

#         self.btn_r3_single = QPushButton("R3 SINGLE")
#         self.btn_r3_capture = QPushButton("Capture R3")

#         btn_row.addWidget(self.btn_r1_single)
#         btn_row.addWidget(self.btn_r1_capture)
#         btn_row.addWidget(self.btn_r2_single)
#         btn_row.addWidget(self.btn_r2_capture)
#         btn_row.addWidget(self.btn_r3_single)
#         btn_row.addWidget(self.btn_r3_capture)

#         layout.addLayout(btn_row)

#         # Button signal connections
#         self.btn_r1_single.clicked.connect(self.on_r1_single)
#         self.btn_r1_capture.clicked.connect(self.on_r1_capture)

#         self.btn_r2_single.clicked.connect(self.on_r2_single)
#         self.btn_r2_capture.clicked.connect(self.on_r2_capture)

#         self.btn_r3_single.clicked.connect(self.on_r3_single)
#         self.btn_r3_capture.clicked.connect(self.on_r3_capture)

#     # ------------------------------------------------------------
#     # Dual-axis setup helper
#     # ------------------------------------------------------------
#     # def _setup_dual_axis(self, pw):
#     #     """
#     #     Adds:
#     #       - CH1 on left Y axis (blue)
#     #       - CH2 on right Y axis (red)
#     #       - Linked X axis
#     #     """

#     #     # CH1 curve (blue)
#     #     ch1 = pw.plot([], [], pen=pg.mkPen('b', width=2))
#     #     self.plot1_ch1 = ch1

#     #     # Secondary ViewBox for CH2 (right axis)
#     #     vb2 = ViewBox()
#     #     pw.scene().addItem(vb2)

#     #     # Show right axis and link it
#     #     pw.showAxis('right')
#     #     pw.getAxis('right').setLabel('CH2', color='r')
#     #     pw.getAxis('right').linkToView(vb2)

#     #     # CH2 curve (red)
#     #     ch2 = PlotCurveItem(pen=pg.mkPen('r', width=2))
#     #     vb2.addItem(ch2)
#     #     self.plot1_ch2 = ch2

#     #     # Link x-axis
#     #     vb2.setXLink(pw)

#         # Fix view changes after resizing
#         # def update_views():
#         #     vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
#         #     vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)

#         # pw.getViewBox().sigResized.connect(update_views)
#         # update_views()

#         # # Export handles to assign later
#         # pw.vb2 = vb2
#         # pw.ch1_curve = ch1
#         # pw.ch2_curve = ch2
#     def _setup_dual_axis(self, pw):
#         """
#         Setup dual-axis plotting for a PlotWidget.
#         Returns:
#             (ch1_curve, ch2_curve)
#         """

#         # CH1 curve (blue, left axis)
#         ch1 = pw.plot([], [], pen=pg.mkPen('b', width=2))

#         # Secondary ViewBox for CH2 (right axis)
#         vb2 = ViewBox()
#         pw.scene().addItem(vb2)

#         pw.showAxis('right')
#         pw.getAxis('right').setLabel('CH2', color='r')
#         pw.getAxis('right').linkToView(vb2)

#         # CH2 curve (red)
#         ch2 = PlotCurveItem(pen=pg.mkPen('r', width=2))
#         vb2.addItem(ch2)

#         # Link X axes
#         vb2.setXLink(pw)

#         # Fix ViewBox geometry
#         def update_views():
#             vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
#             vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)

#         pw.getViewBox().sigResized.connect(update_views)
#         update_views()

#         return ch1, ch2

#     def _apply_font_styling(self):
#         """Apply Times New Roman bold font to all plot axes and labels"""
#         font = QFont("Times New Roman", 12)
#         font.setBold(True)

#         # Style for all three plots
#         for plot in [self.plot1, self.plot2, self.plot3]:
#             # Apply font to axes
#             for axis_name in ('left', 'bottom', 'right'):
#                 axis = plot.getAxis(axis_name)
#                 axis.setStyle(tickFont=font)
#                 axis.setPen('k')
#                 axis.setTextPen('k')

#             # Apply font to axis labels
#             plot.setLabel('left', 'CH1 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
#             plot.setLabel('bottom', 'Time (s)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
#             plot.setLabel('right', 'CH2 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})

#     # ------------------------------------------------------------
#     # Plot update functions (called by main_window)
#     # ------------------------------------------------------------
#     def update_r1(self, t1, v1, t2, v2):
#         self.r1_ch1.setData(t1, v1)
#         self.r1_ch2.setData(t2, v2)

#     def update_r2(self, t1, v1, t2, v2):
#         self.r2_ch1.setData(t1, v1)
#         self.r2_ch2.setData(t2, v2)

#     def update_r3(self, t1, v1, t2, v2):
#         self.r3_ch1.setData(t1, v1)
#         self.r3_ch2.setData(t2, v2)

#     # ------------------------------------------------------------
#     # CLEAR PLOTS
#     # ------------------------------------------------------------
#     def clear_plots(self):
#         self.plot1.clear()
#         self.plot2.clear()
#         self.plot3.clear()

#     # ------------------------------------------------------------
#     # BUTTON HANDLERS — R1
#     # ------------------------------------------------------------
#     def on_r1_single(self):
#         if hasattr(self.parent, "rigol1"):
#             try:
#                 self.parent.rigol1.inst.write(":STOP")
#                 self.parent.rigol1.inst.write(":SINGLE")
#             except Exception as e:
#                 print("R1 SINGLE error:", e)

#     def on_r1_capture(self):
#         if hasattr(self.parent, "on_capture_r1"):
#             self.parent.on_capture_r1()

#     # ------------------------------------------------------------
#     # BUTTON HANDLERS — R2
#     # ------------------------------------------------------------
#     def on_r2_single(self):
#         if hasattr(self.parent, "rigol2"):
#             try:
#                 self.parent.rigol2.inst.write(":STOP")
#                 self.parent.rigol2.inst.write(":SINGLE")
#             except Exception as e:
#                 print("R2 SINGLE error:", e)

#     def on_r2_capture(self):
#         if hasattr(self.parent, "on_capture_r2"):
#             self.parent.on_capture_r2()

#     # ------------------------------------------------------------
#     # BUTTON HANDLERS — R3
#     # ------------------------------------------------------------
#     def on_r3_single(self):
#         if hasattr(self.parent, "rigol3"):
#             try:
#                 self.parent.rigol3.inst.write(":STOP")
#                 self.parent.rigol3.inst.write(":SINGLE")
#             except Exception as e:
#                 print("R3 SINGLE error:", e)

#     def on_r3_capture(self):
#         if hasattr(self.parent, "on_capture_r3"):
#             self.parent.on_capture_r3()
# gui/scope_plot_window.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QLabel, QSpinBox
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from pyqtgraph import ViewBox, PlotCurveItem
from typing import List, Dict, Tuple, Optional
import numpy as np


# Default colors for up to 4 channels
CHANNEL_COLORS = ['b', 'r', 'g', 'm']  # Blue, Red, Green, Magenta
CHANNEL_COLOR_NAMES = ['blue', 'red', 'green', 'magenta']


class MultiChannelPlotWidget(QWidget):
    """
    A plot widget that supports multiple channels with dual Y-axes.
    Channels 1,2 on left axis, Channels 3,4 on right axis (if present).
    """
    
    def __init__(self, title: str = "Scope", num_channels: int = 4, parent=None):
        super().__init__(parent)
        self.title = title
        self.num_channels = min(4, max(1, num_channels))
        self.curves: Dict[int, PlotCurveItem] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create plot widget
        self.plot_widget = pg.PlotWidget(background='w')
        self.plot_widget.setTitle(self.title)
        self.plot_widget.getPlotItem().setContentsMargins(10, 10, 20, 10)
        self.plot_widget.showGrid(x=True, y=True)
        
        # Add legend
        self.legend = self.plot_widget.addLegend()
        
        layout.addWidget(self.plot_widget)
        
        # Create curves for each channel
        self._create_curves()
        
        # Apply font styling
        self._apply_font_styling()
    
    def _create_curves(self):
        """Create curve items for each channel."""
        # Clear existing curves
        self.curves.clear()
        
        # Get the plot item's viewbox
        main_vb = self.plot_widget.getViewBox()
        
        # Create secondary viewbox for channels 3,4 (right axis)
        if self.num_channels > 2:
            self.right_vb = ViewBox()
            self.plot_widget.scene().addItem(self.right_vb)
            self.plot_widget.showAxis('right')
            self.plot_widget.getAxis('right').linkToView(self.right_vb)
            self.right_vb.setXLink(self.plot_widget)
            
            # Fix viewbox geometry on resize
            def update_views():
                self.right_vb.setGeometry(main_vb.sceneBoundingRect())
                self.right_vb.linkedViewChanged(main_vb, self.right_vb.XAxis)
            
            main_vb.sigResized.connect(update_views)
            update_views()
        
        # Create curves
        for i in range(self.num_channels):
            ch_num = i + 1
            color = CHANNEL_COLORS[i]
            pen = pg.mkPen(color, width=2)
            
            if i < 2:
                # Channels 1,2 on left axis (main plot)
                curve = self.plot_widget.plot([], [], pen=pen, name=f"CH{ch_num}")
            else:
                # Channels 3,4 on right axis
                curve = PlotCurveItem(pen=pen)
                self.right_vb.addItem(curve)
                # Add to legend manually
                self.legend.addItem(curve, f"CH{ch_num}")
            
            self.curves[ch_num] = curve
    
    def _apply_font_styling(self):
        """Apply Times New Roman bold font to axes and labels."""
        font = QFont("Times New Roman", 12)
        font.setBold(True)
        
        # Style axes
        for axis_name in ('left', 'bottom', 'right'):
            axis = self.plot_widget.getAxis(axis_name)
            if axis:
                axis.setStyle(tickFont=font)
                axis.setPen('k')
                axis.setTextPen('k')
        
        # Style labels
        label_style = {'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'}
        self.plot_widget.setLabel('left', 'CH1,2 (V)', **label_style)
        self.plot_widget.setLabel('bottom', 'Time (s)', **label_style)
        
        if self.num_channels > 2:
            self.plot_widget.setLabel('right', 'CH3,4 (V)', **label_style)
    
    def update_channel(self, channel: int, t: np.ndarray, v: np.ndarray):
        """
        Update data for a specific channel.
        
        Args:
            channel: Channel number (1-4)
            t: Time array
            v: Voltage array
        """
        if channel in self.curves:
            self.curves[channel].setData(t, v)
    
    def update_all_channels(self, data: Dict[str, Tuple[np.ndarray, np.ndarray]]):
        """
        Update all channels from a dict.
        
        Args:
            data: Dict mapping "CHANx" to (time, voltage) tuples
        """
        for ch_name, (t, v) in data.items():
            # Extract channel number from name like "CHAN1"
            try:
                ch_num = int(ch_name.replace("CHAN", ""))
                self.update_channel(ch_num, t, v)
            except (ValueError, AttributeError):
                pass
    
    def clear(self):
        """Clear all curves."""
        for curve in self.curves.values():
            curve.setData([], [])
    
    def set_num_channels(self, num_channels: int):
        """Change the number of displayed channels."""
        self.num_channels = min(4, max(1, num_channels))
        # Remove existing curves and recreate
        self.plot_widget.clear()
        self._create_curves()
        self._apply_font_styling()


class ScopePlotWindow(QWidget):
    """
    Window displaying waveforms from multiple Rigol oscilloscopes.
    Supports 2 channels per scope.
    """

    def __init__(self, parent=None, num_channels: int = 2, num_scopes: int = 3):
        super().__init__()
        self.parent = parent
        self.num_channels = min(4, max(1, num_channels))
        self.num_scopes = num_scopes
        
        self.setWindowTitle("Oscilloscope Display")
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Channel configuration row
        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Channels per scope:"))
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 4)
        self.channel_spin.setValue(self.num_channels)
        self.channel_spin.valueChanged.connect(self._on_channel_count_changed)
        config_row.addWidget(self.channel_spin)
        config_row.addStretch()
        layout.addLayout(config_row)
        
        # Create plot widgets for each scope
        self.scope_plots: List[MultiChannelPlotWidget] = []
        
        for i in range(self.num_scopes):
            plot = MultiChannelPlotWidget(
                title=f"Rigol #{i+1}",
                num_channels=self.num_channels
            )
            self.scope_plots.append(plot)
            layout.addWidget(plot)
        
        # Legacy aliases for backward compatibility
        if len(self.scope_plots) >= 1:
            self.plot1 = self.scope_plots[0].plot_widget
        if len(self.scope_plots) >= 2:
            self.plot2 = self.scope_plots[1].plot_widget
        if len(self.scope_plots) >= 3:
            self.plot3 = self.scope_plots[2].plot_widget
        
        # Clear button
        self.btn_clear = QPushButton("Clear All Plots")
        self.btn_clear.clicked.connect(self.clear_plots)
        layout.addWidget(self.btn_clear)
        
        # Control buttons row
        btn_row = QHBoxLayout()
        
        # Create buttons for each scope
        self.single_buttons = []
        self.capture_buttons = []
        
        for i in range(self.num_scopes):
            btn_single = QPushButton(f"R{i+1} SINGLE")
            btn_capture = QPushButton(f"Capture R{i+1}")
            
            btn_single.clicked.connect(lambda checked, idx=i: self._on_single(idx))
            btn_capture.clicked.connect(lambda checked, idx=i: self._on_capture(idx))
            
            btn_row.addWidget(btn_single)
            btn_row.addWidget(btn_capture)
            
            self.single_buttons.append(btn_single)
            self.capture_buttons.append(btn_capture)
        
        layout.addLayout(btn_row)
        
        # Legacy button aliases
        if len(self.single_buttons) >= 1:
            self.btn_r1_single = self.single_buttons[0]
            self.btn_r1_capture = self.capture_buttons[0]
        if len(self.single_buttons) >= 2:
            self.btn_r2_single = self.single_buttons[1]
            self.btn_r2_capture = self.capture_buttons[1]
        if len(self.single_buttons) >= 3:
            self.btn_r3_single = self.single_buttons[2]
            self.btn_r3_capture = self.capture_buttons[2]
    
    def _on_channel_count_changed(self, count: int):
        """Handle channel count spinner change."""
        self.num_channels = count
        for plot in self.scope_plots:
            plot.set_num_channels(count)
        
        # Update parent scopes if available
        if self.parent:
            for attr in ['rigol1', 'rigol2', 'rigol3']:
                if hasattr(self.parent, attr):
                    scope = getattr(self.parent, attr)
                    if hasattr(scope, 'set_num_channels'):
                        scope.set_num_channels(count)
    
    def _on_single(self, scope_index: int):
        """Set scope to SINGLE mode."""
        if not self.parent:
            return
        
        scope_attr = f"rigol{scope_index + 1}"
        if hasattr(self.parent, scope_attr):
            try:
                scope = getattr(self.parent, scope_attr)
                scope.inst.write(":STOP")
                scope.inst.write(":SINGLE")
            except Exception as e:
                print(f"R{scope_index+1} SINGLE error:", e)
    
    def _on_capture(self, scope_index: int):
        """Trigger capture for a scope."""
        if not self.parent:
            return
        
        capture_method = f"on_capture_r{scope_index + 1}"
        if hasattr(self.parent, capture_method):
            getattr(self.parent, capture_method)()
    
    # Legacy single button handlers
    def on_r1_single(self):
        self._on_single(0)
    
    def on_r1_capture(self):
        self._on_capture(0)
    
    def on_r2_single(self):
        self._on_single(1)
    
    def on_r2_capture(self):
        self._on_capture(1)
    
    def on_r3_single(self):
        self._on_single(2)
    
    def on_r3_capture(self):
        self._on_capture(2)
    
    # ================================================================
    # Update methods - support both old 2-channel and new N-channel
    # ================================================================
    
    def update_scope(self, scope_index: int, data: Dict[str, Tuple[np.ndarray, np.ndarray]]):
        """
        Update a scope plot with multi-channel data.
        
        Args:
            scope_index: Index of scope (0-2)
            data: Dict mapping "CHANx" to (time, voltage) tuples
        """
        if 0 <= scope_index < len(self.scope_plots):
            self.scope_plots[scope_index].update_all_channels(data)
    
    def update_r1(self, t1=None, v1=None, t2=None, v2=None, data: Optional[Dict] = None):
        """
        Update Rigol #1 plot.
        
        Supports both legacy 2-channel format and new dict format.
        """
        if data is not None:
            self.scope_plots[0].update_all_channels(data)
        else:
            # Legacy format
            if t1 is not None and v1 is not None:
                self.scope_plots[0].update_channel(1, t1, v1)
            if t2 is not None and v2 is not None:
                self.scope_plots[0].update_channel(2, t2, v2)
    
    def update_r2(self, t1=None, v1=None, t2=None, v2=None, data: Optional[Dict] = None):
        """Update Rigol #2 plot."""
        if data is not None:
            self.scope_plots[1].update_all_channels(data)
        else:
            if t1 is not None and v1 is not None:
                self.scope_plots[1].update_channel(1, t1, v1)
            if t2 is not None and v2 is not None:
                self.scope_plots[1].update_channel(2, t2, v2)
    
    def update_r3(self, t1=None, v1=None, t2=None, v2=None, data: Optional[Dict] = None):
        """Update Rigol #3 plot."""
        if data is not None:
            self.scope_plots[2].update_all_channels(data)
        else:
            if t1 is not None and v1 is not None:
                self.scope_plots[2].update_channel(1, t1, v1)
            if t2 is not None and v2 is not None:
                self.scope_plots[2].update_channel(2, t2, v2)
    
    # Legacy curve aliases for backward compatibility
    @property
    def r1_ch1(self):
        return self.scope_plots[0].curves.get(1)
    
    @property
    def r1_ch2(self):
        return self.scope_plots[0].curves.get(2)
    
    @property
    def r2_ch1(self):
        return self.scope_plots[1].curves.get(1)
    
    @property
    def r2_ch2(self):
        return self.scope_plots[1].curves.get(2)
    
    @property
    def r3_ch1(self):
        return self.scope_plots[2].curves.get(1)
    
    @property
    def r3_ch2(self):
        return self.scope_plots[2].curves.get(2)
    
    def clear_plots(self):
        """Clear all scope plots."""
        for plot in self.scope_plots:
            plot.clear()
