import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout


class ScopePlotPanel(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.plot1 = self.make_plot("Rigol #1")
        self.plot2 = self.make_plot("Rigol #2")
        self.plot3 = self.make_plot("Rigol #3")

        layout.addWidget(self.plot1)
        layout.addWidget(self.plot2)
        layout.addWidget(self.plot3)

    def make_plot(self, title):
        plt = pg.PlotWidget()
        plt.setTitle(title)
        plt.showGrid(x=True, y=True)
        plt.setLabel("left", "Voltage (V)")
        plt.setLabel("bottom", "Time (s)")
        return plt
