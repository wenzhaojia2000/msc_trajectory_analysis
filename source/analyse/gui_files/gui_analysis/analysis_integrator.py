# -*- coding: utf-8 -*-
'''
@author: 19081417
'''

from pathlib import Path
import re
import numpy as np
from PyQt5 import QtWidgets, QtCore
from pyqtgraph import BarGraphItem
from .ui_base import AnalysisMainInterface, AnalysisTab

class AnalysisIntegrator(QtWidgets.QWidget, AnalysisTab):
    '''
    Defines functionality for the "Analyse Integrator" tab of the analysis
    GUI.
    '''
    def __init__(self, owner:AnalysisMainInterface) -> None:
        '''
        Initiation method.
        '''
        super().__init__(owner=owner, push_name='analint_push',
                         box_name='analint_layout')
    
    def findObjects(self, push_name, box_name) -> None:
        '''
        Obtains UI elements as instance variables, and possibly some of their
        properties.
        '''
        super().findObjects(push_name, box_name)
        self.timing_box = self.owner.findChild(QtWidgets.QGroupBox, 'timing_box')
        self.timing_sort = self.owner.findChild(QtWidgets.QComboBox, 'timing_combobox')
        self.update_box = self.owner.findChild(QtWidgets.QGroupBox, 'update_box')
        self.update_plot = self.owner.findChild(QtWidgets.QComboBox, 'update_combobox')
        # boxes are hidden initially
        self.timing_box.hide()
        self.update_box.hide()

    def connectObjects(self) -> None:
        '''
        Connects UI elements so they do stuff when interacted with.
        '''
        super().connectObjects()
        # show the update options box when certain result is selected
        for radio in self.radio:
            radio.clicked.connect(self.optionSelected)

    @QtCore.pyqtSlot()
    @AnalysisTab.freezeContinue
    def continuePushed(self) -> None:
        '''
        Action to perform when the tab's 'Continue' button is pushed.
        '''
        # get objectName() of checked radio button (there should only be 1)
        radio_name = [radio.objectName() for radio in self.radio
                      if radio.isChecked()][0]
        match radio_name:
            case 'analint_1': # analyse step size
                self.runCmd('rdsteps')
            case 'analint_2': # look at timing file
                self.rdtiming()
            case 'analint_3': # plot update file step size
                self.rdupdate(plot_error=False)
            case 'analint_4': # plot update file errors
                self.rdupdate(plot_error=True)

    @QtCore.pyqtSlot()
    def optionSelected(self) -> None:
        '''
        Shows per-analysis options if a valid option is checked.
        '''
        options = {1: self.timing_box, 2: self.update_box}
        for radio, box in options.items():
            if self.radio[radio].isChecked():
                box.show()
            else:
                box.hide()

    def rdtiming(self) -> None:
        '''
        Reads the timing file, which is expected to be in the format

        [host, time, directory information]
        Subroutine  Calls N  cpu/N    cpu      %cpu     Clock
        name.1      a.1      b.1      c.1      d.1      e.1
        name.2      a.2      b.2      c.2      d.2      e.2
        ...         ...      ...      ...      ...      ...
        name.m      a.m      b.m      c.m      d.m      e.m

        Total ...
        [any other information]

        name should be a string *with no spaces*, as cells should be seperated
        by spaces. The other cells should be in a numeric form that can be
        converted into a float like 0.123 or 1.234E-10, etc.

        Plots a bar graph of the column selected by the user, and also outputs
        the timing file sorted by the selected column in the text tab.
        '''
        filepath = Path('./timing')
        if filepath.is_file() is False:
            self.owner.showError('FileNotFound: Cannot find timing file in directory')
            return None
        with open(filepath, mode='r', encoding='utf-8') as f:
            text = f.read()
        # split after 'Clock' and before 'Total' (see docstring), so we have
        # three strings, with the middle being the data
        splits = re.split(r'(?<=Clock)\n|\n(?=Total)', text, flags=re.IGNORECASE)
        if len(splits) != 3:
            self.owner.showError('ValueError: Invalid timing file')
            return None
        pre, text, post = splits

        arr = []
        for line in text.split('\n'):
            # should find one name and five floats per line (name, a, b, c, d,
            # e). need to use findall instead of search/match to return just
            # the part in the brackets
            name = re.findall(r'^ *(\S+)', line)
            floats = re.findall(self.float_regex, line)
            if len(name) == 1 and len(floats) == 5:
                # regex returns strings, need to convert into float. the last
                # entry is the line itself, which is already formatted in a
                # nice way. this saves manually formatting the data
                arr.append(tuple(name + list(map(float, floats)) + [line]))
        if len(arr) == 0:
            # nothing found?
            self.owner.showError('ValueError: Invalid timing file')
            return None

        # sort by column chosen by user
        if self.timing_sort.currentIndex() == 0:
            # sort by name
            arr.sort(key=lambda x: x[0])
        else:
            # sort by number (largest first)
            arr.sort(key=lambda x: -x[self.timing_sort.currentIndex()])
        self.owner.data = arr

        # display sorted text
        text = "\n".join([line[-1] for line in self.owner.data])
        self.owner.text.setText(f'{pre}\n{text}\n\n{post}')
        # clear plot
        self.owner.graph.clear()
        self.owner.graph.getPlotItem().enableAutoRange()
        self.owner.slider.hide()

        # start plotting
        self.owner.changePlotTitle('Subroutine timings')
        self.owner.toggleLegend()
        # this is a horizontal bar chart so everything is spun 90 deg. can't
        # do a normal vertical one as pyqtgraph can't rotate tick names (yet)
        if self.timing_sort.currentIndex() == 0:
            # plot cpu if 'name' is selected (names don't have values)
            values = [row[3] for row in self.owner.data]
            self.owner.graph.setLabel('bottom', 'CPU', color='k')
        else:
            values = [row[self.timing_sort.currentIndex()] for row in self.owner.data]
            self.owner.graph.setLabel('bottom', self.timing_sort.currentText(), color='k')
        names = [row[0] for row in self.owner.data]
        positions = list(range(1, len(values)+1))
        bar = BarGraphItem(x0=0, y=positions, height=0.6, width=values)
        self.owner.graph.addItem(bar)
        # sort out bar chart ticks https://stackoverflow.com/questions/72002352
        ticks = []
        for i, label in enumerate(names):
            ticks.append((positions[i], label))
        self.owner.graph.getAxis('left').setTicks([ticks])
        return None

    def rdupdate(self, plot_error:bool=False) -> None:
        '''
        Reads the command output of using rdupdate, which is expected to be in
        the format

        x.1    y1.1    y2.1    y3.1
        x.2    y1.2    y2.2    y3.2
        ...    ...     ...     ...
        x.m    y1.m    y2.m    y3.m

        where x is time, y1 is step size, y2 is error of A, y3 is error of phi.
        Each cell should be in a numeric form that can be converted into a 
        float like 0.123 or 1.234E-10, etc., and cells are seperated with any
        number of spaces (or tabs).

        Plots the step size is plot_error is false, otherwise plots the errors,
        chosen by the self.update_plot combobox.
        '''
        output = self.runCmd('rdupdate')
        if output is None:
            return None
        # assemble data matrix
        arr = []
        for line in output.split('\n'):
            # find all floats in the line
            matches = re.findall(self.float_regex, line)
            # should find four floats per line (x, y1, y2, y3)
            if len(matches) == 4:
                # regex returns strings, need to convert into float
                arr.append(list(map(float, matches)))
        if len(arr) == 0:
            # nothing found: output is likely something else eg. some text
            # like "cannot open or read update file". in which case, don't
            # plot anything
            print('[AnalysisIntegrator.rdupdate] I wasn\'t given any values to plot')
            return None
        self.owner.data = np.array(arr)

        # clear plot and switch tab to show plot
        self.owner.graph.clear()
        self.owner.graph.getPlotItem().enableAutoRange()
        self.owner.tab_widget.setCurrentIndex(1)
        self.owner.slider.hide()

        # start plotting, depending on options
        self.owner.graph.setLabel('bottom', 'Time (fs)', color='k')
        self.owner.toggleLegend()
        if plot_error:
            self.owner.graph.setLabel('left', 'Error', color='k')
            self.owner.changePlotTitle('Update file errors')
            match self.update_plot.currentIndex():
                case 0:
                    self.owner.graph.plot(self.owner.data[:, 0], self.owner.data[:, 2],
                                          name='Error of A-vector', pen='r')
                    self.owner.graph.plot(self.owner.data[:, 0], self.owner.data[:, 3],
                                          name='Error of SPFs', pen='b')
                case 1:
                    self.owner.graph.plot(self.owner.data[:, 0], self.owner.data[:, 2],
                                          name='Error of A-vector', pen='r')
                case 2:
                    self.owner.graph.plot(self.owner.data[:, 0], self.owner.data[:, 3],
                                          name='Error of SPFs', pen='b')
        else:
            self.owner.changePlotTitle('Update file step size')
            self.owner.graph.setLabel('left', 'Step size (fs)', color='k')
            self.owner.graph.plot(self.owner.data[:, 0], self.owner.data[:, 1],
                                  name='Step size', pen='r')
        return None
