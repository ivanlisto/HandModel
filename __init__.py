from .main import HandModelPlugin


def classFactory(iface):
    return HandModelPlugin(iface)
