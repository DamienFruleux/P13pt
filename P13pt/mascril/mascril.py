import sys
import imp
import os
import traceback
from PyQt5.QtCore import (pyqtSlot, pyqtSignal, Qt, QSize, qInstallMessageHandler, QtInfoMsg, QtCriticalMsg, QtDebugMsg,
                          QtWarningMsg, QtFatalMsg, QPoint)
from PyQt5.QtGui import QFont, QTextCursor, QIcon
from PyQt5.QtWidgets import (QWidget, QTextEdit, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout,
                         QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QApplication,
                         QSplitter, QComboBox, QLabel, QHeaderView)
from P13pt.mascril.measurement import MeasurementBase       # we have to import it the same way (from the same parent
                                                            # modules) as we will do it in the acquisition scripts,
                                                            # otherwise they will not be recognised as the same
                                                            # class
from P13pt.mascril.measurement import MeasurementParameter  # idem
from P13pt.mascril.plotter import Plotter
try:
    from PyQt5.QtCore import QString
except ImportError:
    QString = str

import numpy as np

class ReadOnlyConsole(QTextEdit):
    def __init__(self, parent=None):
        super(ReadOnlyConsole, self).__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        font = QFont()
        font.setFamily(u"DejaVu Sans Mono")
        font.setPointSize(10)
        self.setFont(font)

    @pyqtSlot(str)
    def write(self, data):
        """
            This uses insertPlainText (maybe in a later version HTML, so that we can change
            the colour of the output) and scrolls down to the bottom of the field. The problem
            with append() is that it puts the inserted text in its own paragraph, which is not
            good if we do not want the linefeed.
        :param data: a unicode string
        :return: nothing
        """
        # move cursor to end (in case user clicked somewhere else in the window)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)

        while True: # find all carriage returns
            i = data.find('\r')
            if i >= 0: # means we have to deal with a carriage return
                self.insertPlainText(QString(data[0:i]))
                cursor.select(QTextCursor.LineUnderCursor)
                cursor.removeSelectedText()
                data = data[i+1:]
            else:
                break

        # insert remaining text
        self.insertPlainText(data)
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


class mainwindow(QWidget):
    # set up signals
    module_selected = pyqtSignal()
    module_loaded = pyqtSignal()

    def __init__(self, parent=None):
        super(mainwindow, self).__init__(parent)

        # this is where we will store the acquisition module later
        self.m = None

        # set up splitter widget
        l = QVBoxLayout()
        self.setLayout(l)
        self.splitter = QSplitter(self)
        l.addWidget(self.splitter)

        # set up module interface widget
        scriptinterfacewidget = QWidget(self.splitter)
        self.txt_acquisition_script = QLineEdit('Path to acquistion script...')
        self.txt_acquisition_script.setReadOnly(True)
        self.btn_browse = QPushButton(QIcon('../icons/folder.png'), '')
        self.btn_browse.setToolTip('Browse')
        l1 = QHBoxLayout()
        for w in [self.txt_acquisition_script, self.btn_browse]:
            l1.addWidget(w)
        self.btn_load = QPushButton(QIcon('tools-wizard.png'), '')
        self.btn_load.setToolTip('Load module')
        self.btn_run = QPushButton(QIcon('../icons/start.png', ), '')
        self.btn_run.setToolTip('Run module')
        self.btn_stopmod = QPushButton(QIcon('../icons/stop.png'), '')
        self.btn_stopmod.setToolTip('Stop module')
        self.btn_forcestopmod = QPushButton(QIcon('../icons/kill.png'), '')
        self.btn_forcestopmod.setToolTip('Kill module')
        self.btn_help = QPushButton(QIcon('../icons/help.png'), '')
        self.btn_help.setToolTip('Show step-by-step help')
        for btn in [self.btn_load, self.btn_run, self.btn_stopmod, self.btn_forcestopmod, self.btn_help]:
            btn.setIconSize(QSize(32,32))
        for btn in [self.btn_run, self.btn_stopmod, self.btn_forcestopmod]:
            btn.setEnabled(False)
        l2 = QHBoxLayout()
        for w in [self.btn_load, self.btn_run, self.btn_stopmod, self.btn_forcestopmod, self.btn_help]:
            l2.addWidget(w)
        # set up parameters table
        self.lbl_params = QLabel('<b>Module parameters:</b>')
        self.tbl_params = QTableWidget()
        self.tbl_params.setColumnCount(2)
        self.tbl_params.setHorizontalHeaderLabels(['Name', 'Value'])
        self.tbl_params.verticalHeader().hide()
        self.tbl_params.horizontalHeader().setStretchLastSection(True)
        self.lbl_readonlyconsole = QLabel('<b>Terminal output:</b>')
        self.readonlyconsole = ReadOnlyConsole()
        l_siw = QVBoxLayout(scriptinterfacewidget)
        for l in [l1, l2]:
            l_siw.addLayout(l)
        for w in [self.lbl_params, self.tbl_params,
                  self.lbl_readonlyconsole, self.readonlyconsole]:
            l_siw.addWidget(w)

        # set up plotter widget
        self.plotter = Plotter(self.splitter)

        # set up observables widget
        observablesinterfacewidget = QWidget(self.splitter)  # this widget will contain the observables list and the alarms
        # set up observables table
        self.lbl_observables = QLabel('<b>Observables:</b>', observablesinterfacewidget)
        self.tbl_observables = QTableWidget(observablesinterfacewidget)
        self.tbl_observables.setColumnCount(2)
        self.tbl_observables.setHorizontalHeaderLabels(['Name', 'Value'])
        self.tbl_observables.verticalHeader().hide()
        self.tbl_observables.horizontalHeader().setStretchLastSection(True)
        # set up alarms table
        self.lbl_alarm = QLabel('<b>Alarms:</b>', observablesinterfacewidget)
        self.tbl_alarms = QTableWidget(observablesinterfacewidget)
        self.tbl_alarms.setColumnCount(3)
        self.tbl_alarms.setHorizontalHeaderLabels(['Condition', 'Action', 'Value'])
        self.tbl_alarms.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_alarms.verticalHeader().hide()
        self.btn_addalarm = QPushButton("Add alarm", observablesinterfacewidget)
        self.btn_addalarm.setEnabled(False)
        # put everything in a layout
        l = QVBoxLayout(observablesinterfacewidget)
        for w in [self.lbl_observables, self.tbl_observables, self.lbl_alarm, self.tbl_alarms, self.btn_addalarm]:
            l.addWidget(w)

        # make connections
        self.btn_browse.clicked.connect(self.browse_acquisition_script)
        self.btn_load.clicked.connect(self.load_module)
        self.btn_run.clicked.connect(self.run_module)
        self.btn_help.clicked.connect(lambda: self.update_step_help(reinit=True))
        self.btn_addalarm.clicked.connect(self.add_alarm)
        self.tbl_alarms.cellChanged.connect(self.alarm_modified)

        # set window size.
        self.setWindowState(Qt.WindowMaximized)

        # set window title
        self.setWindowTitle("MAScriL - Mercury Acquisition Script Launcher")

        # set up step by step help
        self.lbl_step_help = QLabel(self)
        #self.lbl_step_help.setWindowFlag(Qt.ToolTip)
        self.lbl_step_help.setStyleSheet('QLabel {background-color: #FF6666; padding: 5px; padding-bottom: 15px;}')
        self.lbl_step_help.linkActivated.connect(self.on_step_help_link)
        self.step_help_count = 1

        # set up the step help list: message, reference widget, relative position, signal for next step
        self.step_help = [('Select a module', self.btn_browse, 'bottomright', self.module_selected),
                          ('Load the module', self.btn_load, 'bottomright', self.module_loaded),
                          ('Set the parameters', self.tbl_params, 'bottomright', self.tbl_params.clicked),
                          ('Select X and Y values for plotting', self.plotter.yvar, 'bottomright', self.plotter.yvar.clicked),
                          ('Set up the alarms', self.lbl_alarm, 'topleft', self.tbl_alarms.clicked),
                          ('Run the script', self.btn_run, 'bottomright', self.btn_run.clicked)]

        def make_lambda(i):
            return lambda: self.next_step_help(check_step=i+1, close_last=True)
        for i, step in enumerate(self.step_help):
            step[3].connect(make_lambda(i))

    @pyqtSlot(QString)
    def on_step_help_link(self, str):
        if str == 'close':
            self.lbl_step_help.hide()
            self.step_help_count = 0
        elif str == 'next':
            self.next_step_help()
        else:
            raise Exception('Unsupported link')

    @pyqtSlot()
    def next_step_help(self, check_step=None, close_last=False):
        # check if we should update the step help
        if self.step_help_count == 0 or (check_step and check_step != self.step_help_count):
            return

        # update the step help
        self.step_help_count += 1
        if self.step_help_count > len(self.step_help):
            if close_last:
                self.lbl_step_help.hide()
                self.step_help_count = 0
                return
            else:
                self.step_help_count = 1
        self.update_step_help()


    def update_step_help(self, reinit=False):
        if reinit:
            self.step_help_count = 1
        title = 'Step '+str(self.step_help_count)+':'
        text = self.step_help[self.step_help_count-1][0]
        widget = self.step_help[self.step_help_count-1][1]
        point = self.step_help[self.step_help_count-1][2]
        self.lbl_step_help.setText('<span style="font-size: 16px; font-family: DejaVu Sans;"><b>&#x2196;</b>'+
                                   '<a href="close" style="text-decoration: none;">&#x2716;</a>'+
                                   '<a href="next" style="text-decoration: none;">&#x27a1;</a>'+
                                   '</span>'+
                                   '<div style="margin-left: 10px; margin-right: 10px;">'+
                                       '<b>'+title+'</b><br>'+text+
                                   '</div>')
        self.lbl_step_help.adjustSize()
        if point == 'bottomright':
            self.lbl_step_help.move(widget.mapTo(self, QPoint(widget.width()-5, widget.height()-5)))
        elif point == 'topleft':
            self.lbl_step_help.move(widget.mapTo(self, QPoint(5, 5)))
        else:
            raise Exception("Invalid position")

        self.lbl_step_help.show()

    def paintEvent(self, event):
        super(mainwindow, self).paintEvent(event)
        if self.step_help_count > 0:
            if self.isActiveWindow():
                self.update_step_help()
            else:
                self.lbl_step_help.hide()

    @pyqtSlot()
    def browse_acquisition_script(self):
        modulespath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'modules')
        filename, filt = QFileDialog.getOpenFileName(self, 'Open File', directory=modulespath, filter='*.py')
        if filename:
            self.txt_acquisition_script.setText(filename)
            self.module_selected.emit()

    @pyqtSlot()
    def load_module(self):
        # check if there is a running module
        if isinstance(self.m, MeasurementBase) and self.m.isRunning():
            QMessageBox.critical(self, "Error", "Cannot load a new module when the previous one is not done.")
            return

        # tidy up
        self.tbl_params.clearContents()
        self.plotter.clear()
        self.plotter.xvar.clear()
        self.plotter.yvar.clear()
        self.tbl_observables.clearContents()
        self.tbl_alarms.clearContents()
        for w in [self.btn_run, self.btn_browse, self.btn_load, self.btn_help, self.btn_addalarm]:
            w.setEnabled(False)
        self.tbl_alarms.blockSignals(True)      # we will modify the alarms table, so disable signals

        # indicate we are loading
        self.btn_load.setIcon(QIcon('../icons/wait.png'))
        self.repaint()
        self.plotter.repaint()

        # check if we are dealing with a valid module
        module_loaded = False
        filename = str(self.txt_acquisition_script.text())
        mod_name, file_ext = os.path.splitext(os.path.split(filename)[-1])
        try:
            mod = imp.load_source(mod_name, filename)
            if not hasattr(mod, 'Measurement') or not issubclass(getattr(mod, 'Measurement'), MeasurementBase):
                QMessageBox.critical(self, "Error", "Could not get correct class from file.")
            else:
                module_loaded = True
        except IOError as e:
            QMessageBox.critical(self, "Error", "Could not load file: "+str(e.args[1]))
        except Exception as e:
            QMessageBox.critical(self, "Error", "Could not load module: "+traceback.format_exc())

        if module_loaded:
            self.m = getattr(mod, 'Measurement')(redirect_console=True)

            # set up parameter table
            self.tbl_params.setRowCount(len(self.m.params))
            for i,key in enumerate(self.m.params):
                item = QTableWidgetItem(key)
                item.setFlags(item.flags()^Qt.ItemIsEditable)
                self.tbl_params.setItem(i, 0, item)
                value = self.m.params[key]
                if isinstance(value, list):
                    value = '['+','.join(map(str, value))+']'
                elif isinstance(value, np.ndarray):
                    value = '['+",".join(map(str, value.tolist()))+']'
                if isinstance(value, MeasurementParameter):
                    self.tbl_params.setCellWidget(i, 1, value.widget)
                    value.mainwindow = self
                else:
                    self.tbl_params.setItem(i, 1, QTableWidgetItem(str(value)))

            # set up plotter
            self.plotter.set_header(self.m.observables)

            # set up observables table
            self.tbl_observables.setRowCount(len(self.m.observables))
            for i, label in enumerate(self.m.observables):
                for j in [0, 1]:
                    item = QTableWidgetItem(label if j==0 else '')
                    item.setFlags(item.flags()^Qt.ItemIsEditable)
                    self.tbl_observables.setItem(i, j, item)

            # set up alarms table
            self.tbl_alarms.setRowCount(0)
            for i, alarm in enumerate(self.m.alarms):
                self.add_alarm() # this has the advantage of directly setting up the combobox as well
                self.tbl_alarms.item(i, 0).setText(self.m.alarms[i][0])
                cmb = self.tbl_alarms.cellWidget(i, 1)
                cmb.setCurrentIndex(cmb.findData(self.m.alarms[i][1]))

            # connect signals
            self.m.new_observables_data[list].connect(self.new_data_handler)
            self.m.new_alarm_data[list].connect(self.new_alarm_data_handler)
            self.m.new_console_data[QString].connect(self.readonlyconsole.write)
            self.btn_stopmod.clicked.connect(self.m.quit)
            self.btn_stopmod.clicked.connect(self.quit_requested)
            self.btn_forcestopmod.clicked.connect(self.m.terminate)
            self.m.finished.connect(self.module_done)
            self.tbl_alarms.blockSignals(False)

            # activate run button and add alarm button
            for w in [self.btn_run, self.btn_addalarm]:
                w.setEnabled(True)

            self.module_loaded.emit()

        # activate some other buttons regardless of if the module was successfully loaded
        self.btn_load.setIcon(QIcon('tools-wizard.png'))
        for w in [self.btn_browse, self.btn_load, self.btn_help]:
            w.setEnabled(True)

    @pyqtSlot()
    def run_module(self):
        # check if no other module is running and if the module we loaded is valid
        if isinstance(self.m, MeasurementBase) and self.m.isRunning():
            QMessageBox.critical(self, "Error", "Cannot run a new module when the previous one is not done.")
            return
        elif not isinstance(self.m, MeasurementBase):
            QMessageBox.critical(self, "Error", "Please load a valid module first.")
            return

        # deactivate request_quit flag in case process has been stopped previously
        # and disconnect all signals
        self.m.flags['quit_requested'] = False

        # update the parameters that do not update automatically
        # (i.e. that are not derived from MeasurementParameter)
        for i in range(self.tbl_params.rowCount()):
            key = str(self.tbl_params.item(i, 0).text())
            if not isinstance(self.m.params[key], MeasurementParameter):
                # TODO: get rid of the python interpretation and cast value to the correct type (python evaluation should be a special kind of MeasurementParameter)
                value = self.tbl_params.item(i, 1).text()
                try:
                    self.m.params[key] = eval(value, {'np': np})
                except Exception as e:
                    QMessageBox.critical(self, "Error", "Parameter '"+key+"' could not be evaluated: "+str(e.args[0]))
                    return

        # disable parameter editing
        self.tbl_params.setEnabled(False)

        # update buttons
        self.btn_load.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.btn_stopmod.setEnabled(True)

        # run the thread
        self.m.start()

    def quit_requested(self):
        self.btn_stopmod.setEnabled(False)
        self.btn_forcestopmod.setEnabled(True)

    def module_done(self):
        # enable parameter editing
        self.tbl_params.setEnabled(True)

        # update buttons
        self.btn_stopmod.setEnabled(False)
        self.btn_forcestopmod.setEnabled(False)
        self.btn_run.setEnabled(True)
        self.btn_load.setEnabled(True)

    @pyqtSlot()
    def add_alarm(self):
        # temporarily block the signals while we set up the new row in the alarms table
        blocked = self.tbl_alarms.signalsBlocked()
        self.tbl_alarms.blockSignals(True)

        # create a new row in the alarms table
        self.tbl_alarms.setRowCount(self.tbl_alarms.rowCount() + 1)
        i = self.tbl_alarms.rowCount() - 1

        # create an editable field for the alarm condition
        self.tbl_alarms.setItem(i, 0, QTableWidgetItem())

        # create a combo box for the alarm action
        cmb = QComboBox()
        for value, text in [(MeasurementBase.ALARM_SHOWVALUE, 'show value'),
                            (MeasurementBase.ALARM_QUIT, 'stop acquisition'),
                            (MeasurementBase.ALARM_CALLCOPS, 'call the cops')]:
            cmb.addItem(text, value)
        self.tbl_alarms.setCellWidget(i, 1, cmb)

        # create a non-editable field for the alarm info
        item = QTableWidgetItem()
        item.setFlags(item.flags()^Qt.ItemIsEditable)
        self.tbl_alarms.setItem(i, 2, item)

        # when the QComboBox is changed, we want to emit the cellChanged signal correspondingly
        cmb.currentIndexChanged.connect(lambda: self.tbl_alarms.cellChanged.emit(i, 1))

        # unblock the signals, if they were previously unblocked
        self.tbl_alarms.blockSignals(blocked)

    @pyqtSlot(int, int)
    def alarm_modified(self, row, column):
        # update the alarms
        alarms = []
        for i in range(self.tbl_alarms.rowCount()):
            condition = str(self.tbl_alarms.item(i, 0).text())
            action = self.tbl_alarms.cellWidget(i, 1).currentData()
            alarms.append([condition, action])
        self.m.alarms = alarms

    @pyqtSlot(list)
    def new_data_handler(self, data):
        for i,value in enumerate(data):
            self.tbl_observables.item(i, 1).setText(str(value))
        self.plotter.new_data_handler(data)

    @pyqtSlot(list)
    def new_alarm_data_handler(self, data):
        for i,d in enumerate(data):
            action = self.tbl_alarms.cellWidget(i, 1).currentData()
            result_field = self.tbl_alarms.item(i, 2)
            self.tbl_alarms.item(i, 2).setBackground(Qt.white)
            if isinstance(d, Exception):
                result_field.setText('could not evaluate: '+str(d))
                continue
            if action == MeasurementBase.ALARM_SHOWVALUE:
                result_field.setText(str(d))
            elif action == MeasurementBase.ALARM_QUIT:
                if data[i]:
                    result_field.setText('stopping acquisition...')
                    result_field.setBackground(Qt.red)
            elif action == MeasurementBase.ALARM_CALLCOPS:
                if data[i]:
                    result_field.setText('calling the cops...')
                    result_field.setBackground(Qt.red)
                else:
                    result_field.setText('OK...')
                    result_field.setBackground(Qt.green)

def msghandler(type, context, message):
    if type == QtInfoMsg:
        QMessageBox.information(None, 'Info', message)
    elif type == QtDebugMsg:
        QMessageBox.information(None, 'Debug', message)
    elif type == QtCriticalMsg:
        QMessageBox.critical(None, 'Critical', message)
    elif type == QtWarningMsg:
        QMessageBox.warning(None, 'Warning', message)
    elif type == QtFatalMsg:
        QMessageBox.critical(None, 'Fatal error', message)

def main():
    qInstallMessageHandler(msghandler)

    # CD into directory where this script is saved
    d = os.path.dirname(__file__)
    if d != '': os.chdir(d)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon('tools-wizard.png'))

    w = mainwindow()
    w.show()
     
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
