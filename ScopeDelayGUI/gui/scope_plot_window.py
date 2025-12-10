# # # # gui/scope_plot_window.py
# # # from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
# # # import pyqtgraph as pg


# # # class ScopePlotWindow(QWidget):
# # #     def __init__(self, parent=None):
# # #         super().__init__()
# # #         self.parent = parent

# # #         layout = QVBoxLayout()
# # #         self.setLayout(layout)

# # #         # Existing plot widgets
# # #         self.plot1 = pg.PlotWidget(background='w')
# # #         self.plot2 = pg.PlotWidget(background='w')
# # #         self.plot3 = pg.PlotWidget(background='w')

# # #         layout.addWidget(self.plot1)
# # #         layout.addWidget(self.plot2)
# # #         layout.addWidget(self.plot3)

# # #         # ⭐ Add CLEAR button
# # #         self.btn_clear = QPushButton("Clear All Plots")
# # #         layout.addWidget(self.btn_clear)

# # #         # Connect it
# # #         self.btn_clear.clicked.connect(self.clear_plots)

# # #         # --------------------------------------------------------
# # #         #   BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
# # #         # --------------------------------------------------------
# # #         btn_row = QHBoxLayout()

# # #         # R1 buttons
# # #         self.btn_r1_single = QPushButton("R1 SINGLE")
# # #         self.btn_r1_capture = QPushButton("Capture R1")

# # #         # R2 buttons
# # #         self.btn_r2_single = QPushButton("R2 SINGLE")
# # #         self.btn_r2_capture = QPushButton("Capture R2")

# # #         # R3 buttons
# # #         self.btn_r3_single = QPushButton("R3 SINGLE")
# # #         self.btn_r3_capture = QPushButton("Capture R3")

# # #         # Add all to layout
# # #         btn_row.addWidget(self.btn_r1_single)
# # #         btn_row.addWidget(self.btn_r1_capture)
# # #         btn_row.addWidget(self.btn_r2_single)
# # #         btn_row.addWidget(self.btn_r2_capture)
# # #         btn_row.addWidget(self.btn_r3_single)
# # #         btn_row.addWidget(self.btn_r3_capture)

# # #         layout.addLayout(btn_row)

# # #         # Connect signals to handlers
# # #         self.btn_r1_single.clicked.connect(self.on_r1_single)
# # #         self.btn_r1_capture.clicked.connect(self.on_r1_capture)
# # #         self.btn_r2_single.clicked.connect(self.on_r2_single)
# # #         self.btn_r2_capture.clicked.connect(self.on_r2_capture)
# # #         self.btn_r3_single.clicked.connect(self.on_r3_single)
# # #         self.btn_r3_capture.clicked.connect(self.on_r3_capture)

# # #     def clear_plots(self):
# # #         self.plot1.clear()
# # #         self.plot2.clear()
# # #         self.plot3.clear()

# # #     # ------------------------------------------------------------
# # #     # R1 HANDLERS
# # #     # ------------------------------------------------------------
# # #     def on_r1_single(self):
# # #         if hasattr(self.parent, "rigol1"):
# # #             try:
# # #                 self.parent.rigol1.inst.write(":STOP")
# # #                 self.parent.rigol1.inst.write(":SINGLE")
# # #             except Exception as e:
# # #                 print("R1 SINGLE error:", e)

# # #     def on_r1_capture(self):
# # #         if hasattr(self.parent, "on_capture_r1"):
# # #             self.parent.on_capture_r1()

# # #     # ------------------------------------------------------------
# # #     # R2 HANDLERS
# # #     # ------------------------------------------------------------
# # #     def on_r2_single(self):
# # #         if hasattr(self.parent, "rigol2"):
# # #             try:
# # #                 self.parent.rigol2.inst.write(":STOP")
# # #                 self.parent.rigol2.inst.write(":SINGLE")
# # #             except Exception as e:
# # #                 print("R2 SINGLE error:", e)

# # #     def on_r2_capture(self):
# # #         if hasattr(self.parent, "on_capture_r2"):
# # #             self.parent.on_capture_r2()

# # #     # ------------------------------------------------------------
# # #     # R3 HANDLERS
# # #     # ------------------------------------------------------------
# # #     def on_r3_single(self):
# # #         if hasattr(self.parent, "rigol3"):
# # #             try:
# # #                 self.parent.rigol3.inst.write(":STOP")
# # #                 self.parent.rigol3.inst.write(":SINGLE")
# # #             except Exception as e:
# # #                 print("R3 SINGLE error:", e)

# # #     def on_r3_capture(self):
# # #         if hasattr(self.parent, "on_capture_r3"):
# # #             self.parent.on_capture_r3()


# # # gui/scope_plot_window.py
# # from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
# # from PyQt6.QtGui import QFont
# # import pyqtgraph as pg
# # from pyqtgraph import ViewBox, PlotCurveItem


# # class ScopePlotWindow(QWidget):
# #     def __init__(self, parent=None):
# #         super().__init__()
# #         self.parent = parent

# #         layout = QVBoxLayout()
# #         self.setLayout(layout)

# #         # --------------------------------------------------------
# #         # PLOT 1 (Rigol #1) — dual-axis
# #         # --------------------------------------------------------
# #         # self.plot1 = pg.PlotWidget(background='w')
# #         # layout.addWidget(self.plot1)
# #         # self._setup_dual_axis(self.plot1)
# #         # self.r1_ch1 = self.plot1_ch1
# #         # self.r1_ch2 = self.plot1_ch2

# #         # # --------------------------------------------------------
# #         # # PLOT 2 (Rigol #2)
# #         # # --------------------------------------------------------
# #         # self.plot2 = pg.PlotWidget(background='w')
# #         # layout.addWidget(self.plot2)
# #         # self._setup_dual_axis(self.plot2)
# #         # self.r2_ch1 = self.plot2_ch1
# #         # self.r2_ch2 = self.plot2_ch2

# #         # # --------------------------------------------------------
# #         # # PLOT 3 (Rigol #3)
# #         # # --------------------------------------------------------
# #         # self.plot3 = pg.PlotWidget(background='w')
# #         # layout.addWidget(self.plot3)
# #         # self._setup_dual_axis(self.plot3)
# #         # self.r3_ch1 = self.plot3_ch1
# #         # self.r3_ch2 = self.plot3_ch2
# #         # PLOT 1 (Rigol #1)
# #         self.plot1 = pg.PlotWidget(background='w')
# #         self.plot1.getPlotItem().setContentsMargins(10, 10, 20, 10)
# #         layout.addWidget(self.plot1)
# #         self.r1_ch1, self.r1_ch2 = self._setup_dual_axis(self.plot1)

# #         # PLOT 2 (Rigol #2)
# #         self.plot2 = pg.PlotWidget(background='w')
# #         self.plot2.getPlotItem().setContentsMargins(10, 10, 20, 10)
# #         layout.addWidget(self.plot2)
# #         self.r2_ch1, self.r2_ch2 = self._setup_dual_axis(self.plot2)

# #         # PLOT 3 (Rigol #3)
# #         self.plot3 = pg.PlotWidget(background='w')
# #         self.plot3.getPlotItem().setContentsMargins(10, 10, 20, 10)
# #         layout.addWidget(self.plot3)
# #         self.r3_ch1, self.r3_ch2 = self._setup_dual_axis(self.plot3)

# #         # Apply Times New Roman bold font to all plots
# #         self._apply_font_styling()


# #         # --------------------------------------------------------
# #         # CLEAR button
# #         # --------------------------------------------------------
# #         self.btn_clear = QPushButton("Clear All Plots")
# #         layout.addWidget(self.btn_clear)
# #         self.btn_clear.clicked.connect(self.clear_plots)

# #         # --------------------------------------------------------
# #         # BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
# #         # --------------------------------------------------------
# #         btn_row = QHBoxLayout()

# #         self.btn_r1_single = QPushButton("R1 SINGLE")
# #         self.btn_r1_capture = QPushButton("Capture R1")

# #         self.btn_r2_single = QPushButton("R2 SINGLE")
# #         self.btn_r2_capture = QPushButton("Capture R2")

# #         self.btn_r3_single = QPushButton("R3 SINGLE")
# #         self.btn_r3_capture = QPushButton("Capture R3")

# #         btn_row.addWidget(self.btn_r1_single)
# #         btn_row.addWidget(self.btn_r1_capture)
# #         btn_row.addWidget(self.btn_r2_single)
# #         btn_row.addWidget(self.btn_r2_capture)
# #         btn_row.addWidget(self.btn_r3_single)
# #         btn_row.addWidget(self.btn_r3_capture)

# #         layout.addLayout(btn_row)

# #         # Button signal connections
# #         self.btn_r1_single.clicked.connect(self.on_r1_single)
# #         self.btn_r1_capture.clicked.connect(self.on_r1_capture)

# #         self.btn_r2_single.clicked.connect(self.on_r2_single)
# #         self.btn_r2_capture.clicked.connect(self.on_r2_capture)

# #         self.btn_r3_single.clicked.connect(self.on_r3_single)
# #         self.btn_r3_capture.clicked.connect(self.on_r3_capture)

# #     # ------------------------------------------------------------
# #     # Dual-axis setup helper
# #     # ------------------------------------------------------------
# #     # def _setup_dual_axis(self, pw):
# #     #     """
# #     #     Adds:
# #     #       - CH1 on left Y axis (blue)
# #     #       - CH2 on right Y axis (red)
# #     #       - Linked X axis
# #     #     """

# #     #     # CH1 curve (blue)
# #     #     ch1 = pw.plot([], [], pen=pg.mkPen('b', width=2))
# #     #     self.plot1_ch1 = ch1

# #     #     # Secondary ViewBox for CH2 (right axis)
# #     #     vb2 = ViewBox()
# #     #     pw.scene().addItem(vb2)

# #     #     # Show right axis and link it
# #     #     pw.showAxis('right')
# #     #     pw.getAxis('right').setLabel('CH2', color='r')
# #     #     pw.getAxis('right').linkToView(vb2)

# #     #     # CH2 curve (red)
# #     #     ch2 = PlotCurveItem(pen=pg.mkPen('r', width=2))
# #     #     vb2.addItem(ch2)
# #     #     self.plot1_ch2 = ch2

# #     #     # Link x-axis
# #     #     vb2.setXLink(pw)

# #         # Fix view changes after resizing
# #         # def update_views():
# #         #     vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
# #         #     vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)

# #         # pw.getViewBox().sigResized.connect(update_views)
# #         # update_views()

# #         # # Export handles to assign later
# #         # pw.vb2 = vb2
# #         # pw.ch1_curve = ch1
# #         # pw.ch2_curve = ch2
# #     def _setup_dual_axis(self, pw):
# #         """
# #         Setup dual-axis plotting for a PlotWidget.
# #         Returns:
# #             (ch1_curve, ch2_curve)
# #         """

# #         # CH1 curve (blue, left axis)
# #         ch1 = pw.plot([], [], pen=pg.mkPen('b', width=2))

# #         # Secondary ViewBox for CH2 (right axis)
# #         vb2 = ViewBox()
# #         pw.scene().addItem(vb2)

# #         pw.showAxis('right')
# #         pw.getAxis('right').setLabel('CH2', color='r')
# #         pw.getAxis('right').linkToView(vb2)

# #         # CH2 curve (red)
# #         ch2 = PlotCurveItem(pen=pg.mkPen('r', width=2))
# #         vb2.addItem(ch2)

# #         # Link X axes
# #         vb2.setXLink(pw)

# #         # Fix ViewBox geometry
# #         def update_views():
# #             vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
# #             vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)

# #         pw.getViewBox().sigResized.connect(update_views)
# #         update_views()

# #         return ch1, ch2

# #     def _apply_font_styling(self):
# #         """Apply Times New Roman bold font to all plot axes and labels"""
# #         font = QFont("Times New Roman", 12)
# #         font.setBold(True)

# #         # Style for all three plots
# #         for plot in [self.plot1, self.plot2, self.plot3]:
# #             # Apply font to axes
# #             for axis_name in ('left', 'bottom', 'right'):
# #                 axis = plot.getAxis(axis_name)
# #                 axis.setStyle(tickFont=font)
# #                 axis.setPen('k')
# #                 axis.setTextPen('k')

# #             # Apply font to axis labels
# #             plot.setLabel('left', 'CH1 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
# #             plot.setLabel('bottom', 'Time (s)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
# #             plot.setLabel('right', 'CH2 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})

# #     # ------------------------------------------------------------
# #     # Plot update functions (called by main_window)
# #     # ------------------------------------------------------------
# #     def update_r1(self, t1, v1, t2, v2):
# #         self.r1_ch1.setData(t1, v1)
# #         self.r1_ch2.setData(t2, v2)

# #     def update_r2(self, t1, v1, t2, v2):
# #         self.r2_ch1.setData(t1, v1)
# #         self.r2_ch2.setData(t2, v2)

# #     def update_r3(self, t1, v1, t2, v2):
# #         self.r3_ch1.setData(t1, v1)
# #         self.r3_ch2.setData(t2, v2)

# #     # ------------------------------------------------------------
# #     # CLEAR PLOTS
# #     # ------------------------------------------------------------
# #     def clear_plots(self):
# #         self.plot1.clear()
# #         self.plot2.clear()
# #         self.plot3.clear()

# #     # ------------------------------------------------------------
# #     # BUTTON HANDLERS — R1
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
# #     # BUTTON HANDLERS — R2
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
# #     # BUTTON HANDLERS — R3
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
# # gui/scope_plot_window.py
# from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
# from PyQt6.QtGui import QFont
# import pyqtgraph as pg
# from pyqtgraph import ViewBox, PlotCurveItem


# class ScopePlotWindow(QWidget):
#     def __init__(self, parent=None, **kwargs):
#         super().__init__()
#         self.parent = parent

#         layout = QVBoxLayout()
#         self.setLayout(layout)

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

#         # CLEAR button
#         self.btn_clear = QPushButton("Clear All Plots")
#         layout.addWidget(self.btn_clear)
#         self.btn_clear.clicked.connect(self.clear_plots)

#         # BUTTON BAR FOR R1, R2, R3 SINGLE + CAPTURE
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
#     def update_r1(self, t1, v1, t2, v2, **kwargs):
#         self.r1_ch1.setData(t1, v1)
#         self.r1_ch2.setData(t2, v2)

#     def update_r2(self, t1, v1, t2, v2, **kwargs):
#         self.r2_ch1.setData(t1, v1)
#         self.r2_ch2.setData(t2, v2)

#     def update_r3(self, t1, v1, t2, v2, **kwargs):
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
"""
Scope Plot Window with dual-axis 2-channel display.

Uses pyqtgraph for fast plotting with separate Y-axes for CH1 and CH2.
"""

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont
from pyqtgraph import ViewBox, PlotCurveItem


class ScopePlotWindow(QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__()
        self.parent = parent

        layout = QVBoxLayout()
        self.setLayout(layout)

        # PLOT 1 (Rigol #1)
        self.plot1 = pg.PlotWidget(background='w')
        self.plot1.getPlotItem().setContentsMargins(10, 10, 20, 10)
        layout.addWidget(self.plot1)
        self.r1_ch1, self.r1_ch2 = self._setup_dual_axis(self.plot1)

        # PLOT 2 (Rigol #2)
        self.plot2 = pg.PlotWidget(background='w')
        self.plot2.getPlotItem().setContentsMargins(10, 10, 20, 10)
        layout.addWidget(self.plot2)
        self.r2_ch1, self.r2_ch2 = self._setup_dual_axis(self.plot2)

        # PLOT 3 (Rigol #3)
        self.plot3 = pg.PlotWidget(background='w')
        self.plot3.getPlotItem().setContentsMargins(10, 10, 20, 10)
        layout.addWidget(self.plot3)
        self.r3_ch1, self.r3_ch2 = self._setup_dual_axis(self.plot3)

        # Apply Times New Roman bold font to all plots
        self._apply_font_styling()

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

    def _setup_dual_axis(self, pw):
        """
        Setup dual-axis plotting for a PlotWidget.
        Returns:
            (ch1_curve, ch2_curve)
        """

        # CH1 curve (blue, left axis)
        ch1 = pw.plot([], [], pen=pg.mkPen('b', width=2))

        # Secondary ViewBox for CH2 (right axis)
        vb2 = ViewBox()
        pw.scene().addItem(vb2)

        pw.showAxis('right')
        pw.getAxis('right').setLabel('CH2', color='r')
        pw.getAxis('right').linkToView(vb2)

        # CH2 curve (red)
        ch2 = PlotCurveItem(pen=pg.mkPen('r', width=2))
        vb2.addItem(ch2)

        # Link X axes
        vb2.setXLink(pw)

        # Fix ViewBox geometry
        def update_views():
            vb2.setGeometry(pw.getViewBox().sceneBoundingRect())
            vb2.linkedViewChanged(pw.getViewBox(), vb2.XAxis)

        pw.getViewBox().sigResized.connect(update_views)
        update_views()

        return ch1, ch2

    def _apply_font_styling(self):
        """Apply Times New Roman bold font to all plot axes and labels"""
        font = QFont("Times New Roman", 12)
        font.setBold(True)

        # Style for all three plots
        for plot in [self.plot1, self.plot2, self.plot3]:
            # Apply font to axes
            for axis_name in ('left', 'bottom', 'right'):
                axis = plot.getAxis(axis_name)
                axis.setStyle(tickFont=font)
                axis.setPen('k')
                axis.setTextPen('k')

            # Apply font to axis labels
            plot.setLabel('left', 'CH1 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
            plot.setLabel('bottom', 'Time (s)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
            plot.setLabel('right', 'CH2 (V)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})

    # ------------------------------------------------------------
    # Plot update functions (called by main_window)
    # ------------------------------------------------------------
    def update_r1(self, t1, v1, t2, v2, **kwargs):
        self.r1_ch1.setData(t1, v1)
        self.r1_ch2.setData(t2, v2)

    def update_r2(self, t1, v1, t2, v2, **kwargs):
        self.r2_ch1.setData(t1, v1)
        self.r2_ch2.setData(t2, v2)

    def update_r3(self, t1, v1, t2, v2, **kwargs):
        self.r3_ch1.setData(t1, v1)
        self.r3_ch2.setData(t2, v2)

    # ------------------------------------------------------------
    # CLEAR PLOTS
    # ------------------------------------------------------------
    def clear_plots(self):
        self.plot1.clear()
        self.plot2.clear()
        self.plot3.clear()
        # Re-setup dual axes after clearing
        self.r1_ch1, self.r1_ch2 = self._setup_dual_axis(self.plot1)
        self.r2_ch1, self.r2_ch2 = self._setup_dual_axis(self.plot2)
        self.r3_ch1, self.r3_ch2 = self._setup_dual_axis(self.plot3)
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
