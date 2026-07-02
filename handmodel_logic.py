import os
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer
)
from qgis.PyQt.QtGui import QColor

def classify_hand(output_file, raster_layer, slope_layer, iface,
                  user_classes=None):
    """
    Classifica raster em múltiplas classes de acordo com regras definidas.
    - raster_layer: camada principal (HAND, DEM, etc.)
    - slope_layer: camada slope (se necessário)
    - user_classes: lista de tuplas [(valor, nome, QColor, operador, v1, v2, usar_slope, combinador)]
      onde combinador pode ser "AND", "OR" ou None
    """

    # entrada principal
    entry_r = QgsRasterCalculatorEntry()
    entry_r.ref = 'r@1'
    entry_r.raster = raster_layer
    entry_r.bandNumber = 1

    entries = [entry_r]

    # entrada slope opcional
    if slope_layer:
        entry_s = QgsRasterCalculatorEntry()
        entry_s.ref = 's@1'
        entry_s.raster = slope_layer
        entry_s.bandNumber = 1
        entries.append(entry_s)

    expr_parts = []
    for val, name, color, operator, v1, v2, use_slope, combinador in user_classes:
        ref = entry_r.ref
        cond = None
        op = (operator or "").strip().lower()

        if op == "between":
            cond = f"({ref} >= {v1} AND {ref} <= {v2})"
        elif op in ["equal to", "==", "="]:
            cond = f"({ref} = {v1})"
        elif op in ["not equal to", "!="]:
            cond = f"({ref} != {v1})"
        elif op in ["greater than", ">"]:
            cond = f"({ref} > {v1})"
        elif op in ["less than", "<"]:
            cond = f"({ref} < {v1})"
        elif op in ["greater than or equal to", ">="]:
            cond = f"({ref} >= {v1})"
        elif op in ["less than or equal to", "<="]:
            cond = f"({ref} <= {v1})"

        # se a regra usa slope
        if use_slope and slope_layer and v2:
            cond = f"({cond} AND {entry_s.ref} > {v2})"

        # aplica combinador se houver
        if cond:
            if combinador == "AND" and expr_parts:
                last = expr_parts.pop()
                cond = f"({last} AND {cond})"
            elif combinador == "OR" and expr_parts:
                last = expr_parts.pop()
                cond = f"({last} OR {cond})"

            expr_parts.append(f"(({cond}) * {val})")

    expression = " + ".join(expr_parts)

    calc = QgsRasterCalculator(
        expression,
        output_file,
        'GTiff',
        raster_layer.extent(),
        raster_layer.width(),
        raster_layer.height(),
        entries
    )

    result = calc.processCalculation()

    if result == 0:
        layer = QgsRasterLayer(output_file, "HAND Classification")
        if layer.isValid():
            apply_hand_classification_style(layer, user_classes)
            QgsProject.instance().addMapLayer(layer)
            iface.messageBar().pushMessage(
                "Hand Model",
                f"HAND Classification generated successfully!\nFile saved at: {output_file}",
                level=0
            )
        else:
            iface.messageBar().pushMessage("Hand Model", "File generated, but could not be loaded.", level=2)
    else:
        iface.messageBar().pushMessage("Hand Model", "Error during HAND classification.", level=2)

def apply_hand_classification_style(layer, user_classes=None):
    """
    Aplica simbologia ao raster classificado.
    """

    shader = QgsRasterShader()
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Discrete)

    if user_classes:
        items = [QgsColorRampShader.ColorRampItem(val, color, name)
                 for val, name, color, *_ in user_classes]
    else:
        items = [
            QgsColorRampShader.ColorRampItem(1, QColor(0, 0, 255), "Waterlogged"),
            QgsColorRampShader.ColorRampItem(2, QColor(0, 200, 0), "Ecotone"),
            QgsColorRampShader.ColorRampItem(3, QColor(200, 0, 0), "Slope"),
            QgsColorRampShader.ColorRampItem(4, QColor(255, 255, 0), "Plateau"),
        ]

    color_ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(color_ramp)

    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
