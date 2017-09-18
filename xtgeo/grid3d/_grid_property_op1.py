"""Various grid property operations"""

from __future__ import print_function, absolute_import

import logging
import numpy as np

from xtgeo.common import XTGeoDialog

xtg = XTGeoDialog()

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def get_xy_value_lists(prop, **kwargs):
    """Get values for webportal format

    Two cells:
    [[[(x1,y1), (x2,y2), (x3,y3), (x4,y4)],
    [(x5,y5), (x6,y6), (x7,y7), (x8,y8)]]]

    If mask is True then inactive cells are ommited from the lists,
    else the active cells corners will be present while the property
    will have a -999 value.

    """

    grid = kwargs.get('grid', None)

    mask = kwargs.get('mask', True)

    if grid is None:
        raise RuntimeError('Missing grid object')

    if 'xtgeo' not in repr(grid) or 'Grid' not in repr(grid):
        raise RuntimeError('The input grid is not a XTGeo Grid instance')

    if 'xtgeo' not in repr(prop) or 'GridProperty' not in repr(prop):
        raise RuntimeError('The property is not a XTGeo GridProperty instance')

    clist = grid.get_xyz_corners()
    actnum = grid.get_actnum()

    # set value 0 if actnum is 0 to facilitate later operations
    if mask:
        for i in range(len(clist)):
            clist[i].values[actnum.values == 0] = 0

    # now some numpy operations
    xy0 = np.column_stack((clist[0].values, clist[1].values))
    xy1 = np.column_stack((clist[3].values, clist[4].values))
    xy2 = np.column_stack((clist[6].values, clist[7].values))
    xy3 = np.column_stack((clist[9].values, clist[10].values))

    xyc = np.column_stack((xy0, xy1, xy2, xy3))
    xyc = xyc.reshape(grid.nz, grid.nx * grid.ny, 4, 2)

    coordlist = xyc.tolist()

    # remove cells that are undefined ("marked" as coordinate [0, 0] if mask)
    coordlist = [[[tuple(xy) for xy in cell if xy[0] > 0]
                  for cell in lay] for lay in coordlist]

    coordlist = [[cell for cell in lay if len(cell) > 1] for lay in coordlist]

    pval = prop.values.reshape((grid.nz, grid.nx * grid.ny))
    valuelist = pval.tolist(fill_value=-999.0)
    if mask:
        valuelist = [[val for val in lay if val != -999.0]
                     for lay in valuelist]

    return coordlist, valuelist
