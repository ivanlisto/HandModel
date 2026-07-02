import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QColorDialog, QFileDialog, QListWidget
)
from qgis.core import QgsProject
from qgis.PyQt.QtGui import QColor
from .handmodel_logic import classify_hand


class HandModelDialog(QDialog):
    def __init__(self, iface, plugin, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.plugin = plugin
        self.setWindowTitle("Classification Panel")
        self.resize(700, 500)

        self.layout = QVBoxLayout()

        # Lista no topo para mostrar classes criadas
        self.class_list = QListWidget()
        self.layout.addWidget(self.class_list)

        # Grid principal para definir nova regra
        grid = QGridLayout()

        lbl_class = QLabel("Class Name:")
        lbl_class.setStyleSheet("font-weight: bold")
        self.class_name = QLineEdit("Class#1")

        self.color_button = QPushButton("Set Color")
        self.color_button.setStyleSheet("background-color: red;")
        self.color_button.clicked.connect(self.choose_color)

        lbl_image = QLabel("Image:")
        lbl_image.setStyleSheet("font-weight: bold")
        self.image_combo = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.RasterLayer:
                self.image_combo.addItem(layer.name())

        lbl_operator = QLabel("Operator:")
        lbl_operator.setStyleSheet("font-weight: bold")
        self.operator_combo = QComboBox()
        self.operator_combo.addItems([
            "Between(x>=min && x<=max)", "Equal to(==)", "Not Equal to(!=)",
            "Greater than(>)", "Less than(<)",
            "Greater than or Equal to(>=)", "Less than or Equal to(<=)"
        ])

        lbl_val = QLabel("Values:")
        lbl_val.setStyleSheet("font-weight: bold")
        self.value1 = QLineEdit("0.0")
        self.value2 = QLineEdit("0.0")

        # Botões Set / AND / OR / Delete
        self.set_button = QPushButton("Set")
        self.and_button = QPushButton("AND")
        self.or_button = QPushButton("OR")
        self.delete_button = QPushButton("Delete")

        self.set_button.clicked.connect(self.add_class)
        self.and_button.clicked.connect(self.add_and_condition)
        self.or_button.clicked.connect(self.add_or_condition)
        self.delete_button.clicked.connect(self.delete_class)

        grid.addWidget(lbl_class, 0, 0)
        grid.addWidget(self.class_name, 0, 1)
        grid.addWidget(self.color_button, 0, 2)
        grid.addWidget(lbl_image, 1, 0)
        grid.addWidget(self.image_combo, 1, 1)
        grid.addWidget(lbl_operator, 2, 0)
        grid.addWidget(self.operator_combo, 2, 1)
        grid.addWidget(lbl_val, 3, 0)
        grid.addWidget(self.value1, 3, 1)
        grid.addWidget(self.value2, 3, 2)
        grid.addWidget(self.set_button, 4, 0)
        grid.addWidget(self.and_button, 4, 1)
        grid.addWidget(self.or_button, 4, 2)
        grid.addWidget(self.delete_button, 4, 3)

        self.layout.addLayout(grid)

        # Campo File Name
        file_layout = QGridLayout()
        lbl_file = QLabel("File Name:")
        lbl_file.setStyleSheet("font-weight: bold")
        default_file = self.plugin.output_file("hand_classif")
        self.file_name = QLineEdit(default_file)
        self.save_button = QPushButton("Save As")
        self.save_button.clicked.connect(self.save_file)
        file_layout.addWidget(lbl_file, 0, 0)
        file_layout.addWidget(self.file_name, 0, 1)
        file_layout.addWidget(self.save_button, 0, 2)
        self.layout.addLayout(file_layout)

        # Botões finais
        final_layout = QGridLayout()
        self.load_default_button = QPushButton("Load Default")
        self.cancel_button = QPushButton("Cancel")
        self.apply_button = QPushButton("Apply")
        self.load_default_button.clicked.connect(self.on_load_default)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.on_apply)
        final_layout.addWidget(self.load_default_button, 0, 0)
        final_layout.addWidget(self.cancel_button, 0, 1)
        final_layout.addWidget(self.apply_button, 0, 2)
        self.layout.addLayout(final_layout)

        self.setLayout(self.layout)

        # lista interna de regras
        self.rules = []

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_button.setStyleSheet(
                f"background-color: {color.name()};")

    def add_class(self):
        name = self.class_name.text()
        color = self.color_button.palette().button().color()
        operator = self.operator_combo.currentText()
        v1 = self.value1.text().strip()
        v2 = self.value2.text().strip()
        rule = (len(self.rules)+1, name, color, operator, v1, v2, False, None)
        self.rules.append(rule)
        self.class_list.addItem(f"{name} | {operator} {v1},{v2}")

    def add_and_condition(self):
        name = self.class_name.text()
        color = self.color_button.palette().button().color()
        operator = self.operator_combo.currentText()
        v1 = self.value1.text().strip()
        v2 = self.value2.text().strip()
        rule = (len(self.rules)+1, name, color, operator, v1, v2, False, "AND")
        self.rules.append(rule)
        self.class_list.addItem(f"{name} | {operator} {v1},{v2} (AND)")

    def add_or_condition(self):
        name = self.class_name.text()
        color = self.color_button.palette().button().color()
        operator = self.operator_combo.currentText()
        v1 = self.value1.text().strip()
        v2 = self.value2.text().strip()
        rule = (len(self.rules)+1, name, color, operator, v1, v2, False, "OR")
        self.rules.append(rule)
        self.class_list.addItem(f"{name} | {operator} {v1},{v2} (OR)")

    def delete_class(self):
        row = self.class_list.currentRow()
        if row >= 0:
            self.class_list.takeItem(row)
            self.rules.pop(row)

    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output",
            self.plugin.output_file("hand_classif"),
            "GeoTIFF (*.tif);;All Files (*)"
        )
        if filename:
            self.file_name.setText(filename)

    def on_load_default(self):
        # procura camadas que contenham 'hand' e 'slope' no nome
        hand_layers = [lyr for lyr in QgsProject.instance().mapLayers().values()
                       if lyr.type() == lyr.RasterLayer and "hand" in lyr.name().lower()]
        slope_layers = [lyr for lyr in QgsProject.instance().mapLayers().values()
                        if lyr.type() == lyr.RasterLayer and "slope" in lyr.name().lower()]

        if not hand_layers or not slope_layers:
            self.iface.messageBar().pushMessage("Classification Panel",
                                                "HAND ou Slope não encontrados.", level=2)
            return

        output_file = self.plugin.output_file("hand_classification_default")

        default_classes = [
            (1, "Waterlogged", QColor(0, 0, 255), "between", 0, 5, False, None),
            (2, "Ecotone", QColor(0, 200, 0), "between", 5, 15, False, None),
            (3, "Slope", QColor(200, 0, 0), "greater than", 15, 8, True, "AND"),
            (4, "Plateau", QColor(255, 255, 0),
             "greater than", 15, 8, False, "OR"),
        ]

        classify_hand(
            output_file, hand_layers[0], slope_layers[0], self.iface, default_classes)
        self.accept()

    def on_apply(self):
        if not self.rules:
            self.iface.messageBar().pushMessage("Classification Panel",
                                                "Nenhuma classe definida.", level=2)
            return

        layer_name = self.image_combo.currentText()
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            self.iface.messageBar().pushMessage("Classification Panel",
                                                "Camada não encontrada.", level=2)
            return

        output_file = self.file_name.text().strip()
        if not output_file:
            output_file = self.plugin.output_file("hand_classif")
            self.file_name.setText(output_file)

        classify_hand(output_file, layers[0], None, self.iface, self.rules)
        self.accept()
