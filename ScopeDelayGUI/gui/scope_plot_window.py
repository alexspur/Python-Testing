"""
Scope Plot Window with 4-channel display per oscilloscope.

Uses pyqtgraph for fast plotting with 4 separate Y-axes:
- Left outer axis: CH3 (magenta)
- Left inner axis: CH1 (yellow)
- Right inner axis: CH2 (cyan)
- Right outer axis: CH4 (indigo)
"""

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QCheckBox, QGroupBox
from PyQt6.QtGui import QFont
from pyqtgraph import ViewBox, PlotCurveItem, AxisItem
import numpy as np


class ScopePlotWindow(QWidget):
    """
    Window displaying waveforms from 3 Rigol oscilloscopes, 4 channels each.

    Color scheme:
        CH1 - Yellow
        CH2 - Cyan
        CH3 - Magenta
        CH4 - Indigo
    """

    # Define channel colors as class constants
    CH1_COLOR = '#FFD700'  # Yellow
    CH2_COLOR = '#00FFFF'  # Cyan
    CH3_COLOR = '#FF00FF'  # Magenta
    CH4_COLOR = '#4B0082'  # Indigo

    def __init__(self, parent=None, **kwargs):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Oscilloscope Waveforms (4 Channels)")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Channel visibility checkboxes
        self._create_channel_controls(layout)

        # PLOT 1 (Rigol #1)
        self.plot1 = pg.PlotWidget(background='w')
        self.plot1.setTitle("Rigol #1", color='k', size='12pt')
        layout.addWidget(self.plot1)
        self.r1_curves, self.r1_viewboxes = self._setup_four_channel_plot(self.plot1)

        # PLOT 2 (Rigol #2)
        self.plot2 = pg.PlotWidget(background='w')
        self.plot2.setTitle("Rigol #2", color='k', size='12pt')
        layout.addWidget(self.plot2)
        self.r2_curves, self.r2_viewboxes = self._setup_four_channel_plot(self.plot2)

        # PLOT 3 (Rigol #3)
        self.plot3 = pg.PlotWidget(background='w')
        self.plot3.setTitle("Rigol #3", color='k', size='12pt')
        layout.addWidget(self.plot3)
        self.r3_curves, self.r3_viewboxes = self._setup_four_channel_plot(self.plot3)

        # Apply Times New Roman bold font to all plots
        self._apply_font_styling()

        # Create aliases for backward compatibility
        self.r1_ch1, self.r1_ch2, self.r1_ch3, self.r1_ch4 = self.r1_curves
        self.r2_ch1, self.r2_ch2, self.r2_ch3, self.r2_ch4 = self.r2_curves
        self.r3_ch1, self.r3_ch2, self.r3_ch3, self.r3_ch4 = self.r3_curves

        # CLEAR button
        self.btn_clear = QPushButton("Clear All Plots")
        layout.addWidget(self.btn_clear)
        self.btn_clear.clicked.connect(self.clear_plots)

        # BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
        btn_row = QHBoxLayout()

        self.btn_r1_single = QPushButton("R1 SINGLE")
        self.btn_r1_capture = QPushButton("Capture R1")

        self.btn_r2_single = QPushButton("R2 SINGLE")
        self.btn_r2_capture = QPushButton("Capture R2")

        self.btn_r3_single = QPushButton("R3 SINGLE")
        self.btn_r3_capture = QPushButton("Capture R3")

        btn_row.addWidget(self.btn_r1_single)
        btn_row.addWidget(self.btn_r1_capture)
        btn_row.addWidget(self.btn_r2_single)
        btn_row.addWidget(self.btn_r2_capture)
        btn_row.addWidget(self.btn_r3_single)
        btn_row.addWidget(self.btn_r3_capture)

        layout.addLayout(btn_row)

        # Button signal connections
        self.btn_r1_single.clicked.connect(self.on_r1_single)
        self.btn_r1_capture.clicked.connect(self.on_r1_capture)

        self.btn_r2_single.clicked.connect(self.on_r2_single)
        self.btn_r2_capture.clicked.connect(self.on_r2_capture)

        self.btn_r3_single.clicked.connect(self.on_r3_single)
        self.btn_r3_capture.clicked.connect(self.on_r3_capture)

    # def _create_channel_controls(self, layout):
    #     """Create channel visibility controls with default OS checkboxes"""
    #     control_box = QGroupBox("Channel Visibility")
    #     control_layout = QHBoxLayout()
    #     control_box.setLayout(control_layout)
    #     # cb = QCheckBox(name)
    #     # cb.setChecked(True)

    #     # # Force native OS checkbox rendering
    #     # cb.setStyleSheet("QCheckBox { background: transparent; }")
    #     # cb.setAttribute(cb.WA_StyledBackground, False)

    #     # Channel checkboxes - default appearance
    #     self.ch_visible = [True, True, True, True]
    #     self.ch_checkboxes = []

    #     ch_names = ['CH1 (Yellow)', 'CH2 (Cyan)', 'CH3 (Magenta)', 'CH4 (Indigo)']

    #     for i, name in enumerate(ch_names):
    #         cb = QCheckBox(name)
    #         cb.setChecked(True)
    #         # Remove stylesheet to use default OS appearance
    #         cb.setStyleSheet("")
    #         cb.stateChanged.connect(lambda state, idx=i: self._toggle_channel(idx, state))
    #         control_layout.addWidget(cb)
    #         self.ch_checkboxes.append(cb)

    #     control_layout.addStretch()
    #     layout.addWidget(control_box)
    def _create_channel_controls(self, layout):
        """Create channel visibility controls with black text on white background"""
        control_box = QGroupBox("Channel Visibility")
        control_box.setStyleSheet("""
            QGroupBox {
                color: black;
                background-color: white;
            }
            QCheckBox {
                color: black;
                background-color: white;
            }
        """)
        control_layout = QHBoxLayout()
        control_box.setLayout(control_layout)

        self.ch_visible = [True, True, True, True]
        self.ch_checkboxes = []

        ch_names = ['CH1 (Yellow)', 'CH2 (Cyan)', 'CH3 (Magenta)', 'CH4 (Indigo)']

        for i, name in enumerate(ch_names):
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, idx=i: self._toggle_channel(idx, state))

            control_layout.addWidget(cb)
            self.ch_checkboxes.append(cb)

        control_layout.addStretch()
        layout.addWidget(control_box)


    def _toggle_channel(self, channel_idx, state):
        """Toggle visibility of a channel across all plots"""
        # state is an int: 0=Unchecked, 2=Checked (1=PartiallyChecked)
        visible = state == 2
        self.ch_visible[channel_idx] = visible

        # Update all plots
        for curves in [self.r1_curves, self.r2_curves, self.r3_curves]:
            if curves[channel_idx] is not None:
                curves[channel_idx].setVisible(visible)

    def _setup_four_channel_plot(self, pw):
        """
        Setup 4-channel plotting for a PlotWidget with 4 separate Y-axes.

        Layout (from left to right):
        - Column 1: CH1 axis (Yellow) - left (default)
        - Column 2: Plot area
        - Column 3: CH2 axis (Cyan) - right inner (default)
        - Column 4: CH3 axis (Magenta) - right middle
        - Column 5: CH4 axis (Indigo) - right outer

        Returns:
            Tuple of (curves, viewboxes)
            curves = (ch1_curve, ch2_curve, ch3_curve, ch4_curve)
            viewboxes = (vb_ch2, vb_ch3, vb_ch4)
        """
        plotItem = pw.getPlotItem()

        # Create pens for each channel
        ch1_pen = pg.mkPen(self.CH1_COLOR, width=2)
        ch2_pen = pg.mkPen(self.CH2_COLOR, width=2)
        ch3_pen = pg.mkPen(self.CH3_COLOR, width=2)
        ch4_pen = pg.mkPen(self.CH4_COLOR, width=2)

        # CH1 uses the default left axis
        ch1 = pw.plot([], [], pen=ch1_pen, name='CH1')

        # Style the default left axis for CH1 (yellow)
        ax_ch1 = pw.getAxis('left')
        ax_ch1.setPen(pg.mkPen(self.CH1_COLOR, width=2))
        ax_ch1.setTextPen(pg.mkPen(self.CH1_COLOR))
        ax_ch1.setLabel('CH1 (V)', color=self.CH1_COLOR)
        ax_ch1.setWidth(60)

        # Create ViewBox and axis for CH2 using default right axis (cyan)
        vb_ch2 = ViewBox()
        pw.showAxis('right')
        ax_ch2 = pw.getAxis('right')
        ax_ch2.setPen(pg.mkPen(self.CH2_COLOR, width=2))
        ax_ch2.setTextPen(pg.mkPen(self.CH2_COLOR))
        ax_ch2.setLabel('CH2 (V)', color=self.CH2_COLOR)
        ax_ch2.setWidth(55)
        ax_ch2.linkToView(vb_ch2)
        plotItem.scene().addItem(vb_ch2)
        vb_ch2.setXLink(pw)

        ch2 = PlotCurveItem(pen=ch2_pen, name='CH2')
        vb_ch2.addItem(ch2)

        # Create ViewBox and axis for CH3 (right middle - magenta)
        vb_ch3 = ViewBox()
        ax_ch3 = AxisItem('right')
        ax_ch3.setPen(pg.mkPen(self.CH3_COLOR, width=2))
        ax_ch3.setTextPen(pg.mkPen(self.CH3_COLOR))
        ax_ch3.setLabel('CH3 (V)', color=self.CH3_COLOR)
        ax_ch3.setWidth(55)
        ax_ch3.linkToView(vb_ch3)
        plotItem.scene().addItem(vb_ch3)
        vb_ch3.setXLink(pw)
        plotItem.layout.addItem(ax_ch3, 2, 4)

        ch3 = PlotCurveItem(pen=ch3_pen, name='CH3')
        vb_ch3.addItem(ch3)

        # Create ViewBox and axis for CH4 (right outer - indigo)
        vb_ch4 = ViewBox()
        ax_ch4 = AxisItem('right')
        ax_ch4.setPen(pg.mkPen(self.CH4_COLOR, width=2))
        ax_ch4.setTextPen(pg.mkPen(self.CH4_COLOR))
        ax_ch4.setLabel('CH4 (V)', color=self.CH4_COLOR)
        ax_ch4.setWidth(55)
        ax_ch4.linkToView(vb_ch4)
        plotItem.scene().addItem(vb_ch4)
        vb_ch4.setXLink(pw)
        plotItem.layout.addItem(ax_ch4, 2, 5)

        ch4 = PlotCurveItem(pen=ch4_pen, name='CH4')
        vb_ch4.addItem(ch4)

        # Store axis references
        pw.ax_ch1 = ax_ch1
        pw.ax_ch2 = ax_ch2
        pw.ax_ch3 = ax_ch3
        pw.ax_ch4 = ax_ch4

        # Fix ViewBox geometry on resize
        def update_views():
            rect = pw.getViewBox().sceneBoundingRect()
            for vb in [vb_ch2, vb_ch3, vb_ch4]:
                vb.setGeometry(rect)
                vb.linkedViewChanged(pw.getViewBox(), vb.XAxis)

        pw.getViewBox().sigResized.connect(update_views)
        update_views()

        # Store viewbox references
        pw.vb_ch2 = vb_ch2
        pw.vb_ch3 = vb_ch3
        pw.vb_ch4 = vb_ch4

        # Add legend
        legend = pw.addLegend(offset=(70, 30))
        legend.addItem(ch1, 'CH1')
        legend.addItem(ch2, 'CH2')
        legend.addItem(ch3, 'CH3')
        legend.addItem(ch4, 'CH4')

        return (ch1, ch2, ch3, ch4), (vb_ch2, vb_ch3, vb_ch4)

    def _apply_font_styling(self):
        """Apply Times New Roman bold font to all plot axes and labels"""
        font = QFont("Times New Roman", 10)
        font.setBold(True)

        # Style for all three plots
        for plot in [self.plot1, self.plot2, self.plot3]:
            plotItem = plot.getPlotItem()

            # Apply font to bottom axis
            plot.getAxis('bottom').setStyle(tickFont=font)
            plot.setLabel('bottom', 'Time (s)', **{'font-size': '10pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})

            # Apply font to left axis (CH1)
            plot.getAxis('left').setStyle(tickFont=font)

            # Apply font to right axis (CH2)
            plot.getAxis('right').setStyle(tickFont=font)

            # Apply font to additional axes if they exist in the layout
            for i in range(plotItem.layout.count()):
                item = plotItem.layout.itemAt(i)
                if isinstance(item, AxisItem):
                    item.setStyle(tickFont=font)

    # ------------------------------------------------------------
    # Plot update functions (called by main_window)
    # ------------------------------------------------------------
    def update_r1(self, t1, v1, t2, v2, t3=None, v3=None, t4=None, v4=None, **kwargs):
        """Update Rigol #1 plot with up to 4 channels"""
        self.r1_ch1.setData(t1, v1)
        self.r1_ch2.setData(t2, v2)

        if t3 is not None and v3 is not None and len(t3) > 0:
            self.r1_ch3.setData(t3, v3)
        else:
            self.r1_ch3.setData([], [])

        if t4 is not None and v4 is not None and len(t4) > 0:
            self.r1_ch4.setData(t4, v4)
        else:
            self.r1_ch4.setData([], [])

    def update_r2(self, t1, v1, t2, v2, t3=None, v3=None, t4=None, v4=None, **kwargs):
        """Update Rigol #2 plot with up to 4 channels"""
        self.r2_ch1.setData(t1, v1)
        self.r2_ch2.setData(t2, v2)

        if t3 is not None and v3 is not None and len(t3) > 0:
            self.r2_ch3.setData(t3, v3)
        else:
            self.r2_ch3.setData([], [])

        if t4 is not None and v4 is not None and len(t4) > 0:
            self.r2_ch4.setData(t4, v4)
        else:
            self.r2_ch4.setData([], [])

    def update_r3(self, t1, v1, t2, v2, t3=None, v3=None, t4=None, v4=None, **kwargs):
        """Update Rigol #3 plot with up to 4 channels"""
        self.r3_ch1.setData(t1, v1)
        self.r3_ch2.setData(t2, v2)

        if t3 is not None and v3 is not None and len(t3) > 0:
            self.r3_ch3.setData(t3, v3)
        else:
            self.r3_ch3.setData([], [])

        if t4 is not None and v4 is not None and len(t4) > 0:
            self.r3_ch4.setData(t4, v4)
        else:
            self.r3_ch4.setData([], [])

    def update_r1_four(self, data):
        """Update Rigol #1 with 4-channel data tuple"""
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        self.update_r1(t1, v1, t2, v2, t3, v3, t4, v4)

    def update_r2_four(self, data):
        """Update Rigol #2 with 4-channel data tuple"""
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        self.update_r2(t1, v1, t2, v2, t3, v3, t4, v4)

    def update_r3_four(self, data):
        """Update Rigol #3 with 4-channel data tuple"""
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        self.update_r3(t1, v1, t2, v2, t3, v3, t4, v4)

    # ------------------------------------------------------------
    # CLEAR PLOTS
    # ------------------------------------------------------------
    def clear_plots(self):
        """Clear all plots data"""
        # Clear data from existing curves
        for curves in [self.r1_curves, self.r2_curves, self.r3_curves]:
            for curve in curves:
                if curve is not None:
                    curve.setData([], [])

    def full_clear_plots(self):
        """Full clear with plot reconstruction (use if clear_plots doesn't work)"""
        self.plot1.clear()
        self.plot2.clear()
        self.plot3.clear()

        # Re-setup axes after clearing
        self.r1_curves, self.r1_viewboxes = self._setup_four_channel_plot(self.plot1)
        self.r2_curves, self.r2_viewboxes = self._setup_four_channel_plot(self.plot2)
        self.r3_curves, self.r3_viewboxes = self._setup_four_channel_plot(self.plot3)

        # Update aliases
        self.r1_ch1, self.r1_ch2, self.r1_ch3, self.r1_ch4 = self.r1_curves
        self.r2_ch1, self.r2_ch2, self.r2_ch3, self.r2_ch4 = self.r2_curves
        self.r3_ch1, self.r3_ch2, self.r3_ch3, self.r3_ch4 = self.r3_curves

        self._apply_font_styling()

    # ------------------------------------------------------------
    # BUTTON HANDLERS — R1
    # ------------------------------------------------------------
    def on_r1_single(self):
        if hasattr(self.parent, "rigol1"):
            try:
                self.parent.rigol1.single()
            except Exception as e:
                print("R1 SINGLE error:", e)

    def on_r1_capture(self):
        if hasattr(self.parent, "on_capture_r1"):
            self.parent.on_capture_r1()

    # ------------------------------------------------------------
    # BUTTON HANDLERS — R2
    # ------------------------------------------------------------
    def on_r2_single(self):
        if hasattr(self.parent, "rigol2"):
            try:
                self.parent.rigol2.single()
            except Exception as e:
                print("R2 SINGLE error:", e)

    def on_r2_capture(self):
        if hasattr(self.parent, "on_capture_r2"):
            self.parent.on_capture_r2()

    # ------------------------------------------------------------
    # BUTTON HANDLERS — R3
    # ------------------------------------------------------------
    def on_r3_single(self):
        if hasattr(self.parent, "rigol3"):
            try:
                self.parent.rigol3.single()
            except Exception as e:
                print("R3 SINGLE error:", e)

    def on_r3_capture(self):
        if hasattr(self.parent, "on_capture_r3"):
            self.parent.on_capture_r3()