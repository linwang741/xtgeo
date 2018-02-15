"""Do gridding from 3D parameters"""

import numpy as np
import numpy.ma as ma
import scipy.interpolate

import cxtgeo.cxtgeo as _cxtgeo
import xtgeo

xtg = xtgeo.common.XTGeoDialog()

logger = xtg.functionlogger(__name__)

# Note: 'self' is an instance of RegularSurface


def points_gridding(self, points, method='linear', coarsen=1):
    """Do gridding from a points data set."""

    xi, yi = self.get_xy_values()

    df = points.dataframe

    xc = df['X_UTME'].values
    yc = df['Y_UTMN'].values
    zc = df['Z_TVDSS'].values

    if coarsen > 1:
        xc = xc[::coarsen]
        yc = yc[::coarsen]
        zc = zc[::coarsen]

    logger.info('Length of xc array: {}'.format(xc.size))

    validmethods = ['linear', 'nearest', 'cubic']
    if method not in set(validmethods):
        raise ValueError('Invalid method for gridding: {}, valid '
                         'options are {}'. format(method, validmethods))

    try:
        znew = scipy.interpolate.griddata((xc, yc), zc, (xi, yi),
                                          method=method, fill_value=np.nan)
    except ValueError as verr:
        raise RuntimeError('Could not do gridding: {}'.format(verr))

    logger.info('Gridding point ... DONE')

    znew = self.ensure_correct_values(self.ncol, self.nrow, znew)

    self.values = znew


def avg_from_3d_prop_gridding(self, xprop=None, yprop=None,
                              mprop=None, dzprop=None, layer_minmax=None,
                              truncate_le=None, zoneprop=None,
                              zone_minmax=None,
                              sampling=1):

    # TODO:
    # - Refactoring, shorten routine
    # - Clarify the use of ordinary numpies vs masked
    # - speed up gridding if possible

    ncol, nrow, nlay = xprop.shape

    if layer_minmax is None:
        layer_minmax = (1, 99999)

    if zone_minmax is None:
        zone_minmax = (1, 99999)

    usezoneprop = True
    if zoneprop is None:
        usezoneprop = False

    # avoid artifacts from inactive cells that slips through somehow...
    dzprop[mprop > _cxtgeo.UNDEF_LIMIT] = 0.0

    logger.info('Layer from: {}'.format(layer_minmax[0]))
    logger.info('Layer to: {}'.format(layer_minmax[1]))
    logger.debug('Layout is {} {} {}'.format(ncol, nrow, nlay))

    logger.info('Zone from: {}'.format(zone_minmax[0]))
    logger.info('Zone to: {}'.format(zone_minmax[1]))
    logger.info('Zone is :')
    logger.info(zoneprop)

    xi, yi = self.get_xy_values()

    sf = sampling

    logger.debug('ZONEPROP:')
    logger.debug(zoneprop)
    # compute per K layer (start on count 1)

    first = True
    for k in range(1, nlay + 1):

        if k < layer_minmax[0] or k > layer_minmax[1]:
            logger.info('SKIP LAYER {}'.format(k))
            continue
        else:
            logger.info('USE LAYER {}'.format(k))

        if usezoneprop:
            zonecopy = ma.copy(zoneprop[::sf, ::sf, k - 1:k])

            zzz = int(round(zonecopy.mean()))
            if zzz < zone_minmax[0] or zzz > zone_minmax[1]:
                continue

        logger.info('Mapping for ' + str(k) + '...')

        xcopy = np.copy(xprop[::, ::, k - 1:k])
        ycopy = np.copy(yprop[::, ::, k - 1:k])
        zcopy = np.copy(mprop[::, ::, k - 1:k])
        dzcopy = np.copy(dzprop[::, ::, k - 1:k])

        if first:
            wsum = np.zeros((self._ncol, self._nrow), order='F')
            dzsum = np.zeros((self._ncol, self._nrow), order='F')
            first = False

        logger.debug(zcopy)

        xc = np.reshape(xcopy, -1, order='F')
        yc = np.reshape(ycopy, -1, order='F')
        zv = np.reshape(zcopy, -1, order='F')
        dz = np.reshape(dzcopy, -1, order='F')

        zvdz = zv * dz

        try:
            zvdzi = scipy.interpolate.griddata((xc[::sf], yc[::sf]),
                                               zvdz[::sf],
                                               (xi, yi),
                                               method='linear',
                                               fill_value=0.0)
        except ValueError:
            continue

        try:
            dzi = scipy.interpolate.griddata((xc[::sf], yc[::sf]),
                                             dz[::sf],
                                             (xi, yi),
                                             method='linear',
                                             fill_value=0.0)
        except ValueError:
            continue

        logger.debug(zvdzi.shape)
        zvdzi = np.asfortranarray(zvdzi)
        dzi = np.asfortranarray(dzi)
        logger.debug('ZVDVI shape {}'.format(zvdzi.shape))
        logger.debug('ZVDZI flags {}'.format(zvdzi.flags))

        wsum = wsum + zvdzi
        dzsum = dzsum + dzi

        logger.debug(wsum[0:20, 0:20])

    dzsum[dzsum == 0.0] = 1e-20
    vv = wsum / dzsum
    vv = ma.masked_invalid(vv)
    if truncate_le:
        vv = ma.masked_less(vv, truncate_le)

    self.values = vv


def hc_thickness_3dprops_gridding(self, xprop=None, yprop=None,
                                  hcpfzprop=None, zoneprop=None,
                                  zone_minmax=None, layer_minmax=None,
                                  zone_avg=False, coarsen=1):

    # NOTE:_
    # - Inputs are pure 3D numpies, not masked!
    # - Xprop and yprop must be made for all cells

    for a in [hcpfzprop, xprop, yprop, zoneprop]:
        logger.debug('xxx MIN MAX MEAN {} {} {}'.
                     format(a.min(), a.max(), a.mean()))

    if zone_minmax is None:
        raise ValueError('zone_minmax is required')

    xprop, yprop, hcpfzprop, zoneprop = _zone_hc_averaging(
        xprop, yprop, hcpfzprop, zoneprop, zone_minmax, coarsen, zone_avg)

    ncol, nrow, nlay = xprop.shape

    if layer_minmax is None:
        layer_minmax = (1, nlay)
    else:
        if layer_minmax is not None and zone_avg:
            raise RuntimeError('Cannot combine layer_minmax and zone_avg')

        minmax = list(layer_minmax)
        if minmax[0] < 1:
            minmax[0] = 1
        if minmax[1] > nlay:
            minmax[1] = nlay
        layer_minmax = tuple(minmax)

    logger.debug('Grid layout is {} {} {}'.format(ncol, nrow, nlay))

    # rotation in mesh coords are OK!
    xi, yi = self.get_xy_values()

    # filter and compute per K layer (start count on 0)
    for k0 in range(layer_minmax[0] - 1, layer_minmax[1]):

        k1 = k0 + 1   # layer counting base is 1 for k1

        logger.info('Mapping for (combined) layer no ' + str(k1) + '...')

        if k1 == layer_minmax[0]:
            logger.info('Initialize zsum ...')
            zsum = np.zeros((self._ncol, self._nrow), order='F')

        # this should actually never happen...
        if k1 < layer_minmax[0] or k1 > layer_minmax[1]:
            logger.warning('SKIP (layer_minmax)')
            continue

        if zoneprop is not None:
            zoneslice = zoneprop[:, :, k0]

            actz = int(round(zoneslice.mean()))
            if actz < zone_minmax[0] or actz > zone_minmax[1]:
                logger.info('SKIP (not active zone)')
                continue

        # get slices per layer of relevant props
        xcopy = np.copy(xprop[:, :, k0], order='F')
        ycopy = np.copy(yprop[:, :, k0], order='F')
        zcopy = np.copy(hcpfzprop[:, :, k0], order='F')

        propsum = zcopy.sum()
        if (abs(propsum) < 1e-12):
            logger.info('Too little HC, skip layer K = {}'.format(k1))
            continue
        else:
            logger.debug('Z property sum is {}'.format(propsum))

        # need to make arrays 1D
        logger.debug('Reshape and filter ...')
        x = np.reshape(xcopy, -1, order='F')
        y = np.reshape(ycopy, -1, order='F')
        z = np.reshape(zcopy, -1, order='F')

        xc = xcopy.flatten(order='F')

        x = x[xc < self._undef_limit]
        y = y[xc < self._undef_limit]
        z = z[xc < self._undef_limit]

        logger.debug('Reshape and filter ... done')

        logger.debug('Map ... layer = {}'.format(k1))

        try:
            zi = scipy.interpolate.griddata((x, y), z, (xi, yi),
                                            method='linear',
                                            fill_value=0.0)
        except ValueError as ve:
            logger.info('Not able to grid layer {} ({})'.format(k1, ve))
            continue

        zi = np.asfortranarray(zi)
        logger.info('ZI shape is {} and flags {}'.format(zi.shape, zi.flags))

        zsum = zsum + zi
        logger.info('Sum of HCPB layer is {}'.format(zsum.mean()))

    self.values = zsum

    logger.info('Exit from hc_thickness_from_3dprops')

    return True


def _zone_hc_averaging(xprop, yprop, hcpfzprop, zoneprop, zone_minmax,
                       coarsen, zone_avg):

    # Change the 3D numpy array so they get layers by
    # averaging across zones. This may speed up a lot,
    # but will reduce the resolution.
    # The x y coordinates shall be averaged (ideally
    # with thickness weigting...) while hcpfzprop
    # must be summed.

    logger.info('HPR initial sum is {}'.format(hcpfzprop.sum()))

    xpr = xprop
    ypr = yprop
    zpr = zoneprop
    hpr = hcpfzprop

    for a in [xpr, ypr, hpr, zpr]:
        logger.info('Input shape of ... is {}'.format(a.shape))

    if coarsen > 1:
        xpr = xprop[::coarsen, ::coarsen, ::].copy(order='F')
        ypr = yprop[::coarsen, ::coarsen, ::].copy(order='F')
        hpr = hcpfzprop[::coarsen, ::coarsen, ::].copy(order='F')
        zpr = zoneprop[::coarsen, ::coarsen, ::].copy(order='F')

    if coarsen > 1:
        logger.info('Coarsen is {}'.format(coarsen))

    if zone_avg:
        logger.info('Tuning zone_avg is {}'.format(zone_avg))
        zmin = int(zone_minmax[0])
        zmax = int(zone_minmax[1])
        newx = []
        newy = []
        newz = []
        newh = []

        logger.info('HPR1: {}'.format(hpr.sum()))

        for iz in range(zmin, zmax + 1):
            xpr2 = ma.masked_where(zpr != iz, xpr)
            ypr2 = ma.masked_where(zpr != iz, ypr)
            hpr2 = ma.masked_where(zpr != iz, hpr)
            logger.info('HPR2 IZ is = {} {}'.format(iz, hpr2.sum()))
            zpr2 = ma.masked_where(zpr != iz, zpr)

            xpr2 = ma.average(xpr2, axis=2)
            ypr2 = ma.average(ypr2, axis=2)
            hpr2 = ma.sum(hpr2, axis=2)
            zpr2 = ma.average(zpr2, axis=2)

            newx.append(xpr2)
            newy.append(ypr2)
            newh.append(hpr2)
            newz.append(zpr2)

        xpr = ma.dstack(newx)
        ypr = ma.dstack(newy)
        hpr = ma.dstack(newh)
        zpr = ma.dstack(newz)

    logger.info('HPR afterwards sum is {}'.format(hpr.sum()))

    xpr = ma.filled(xpr, fill_value=np.nan)
    ypr = ma.filled(ypr, fill_value=np.nan)
    hpr = ma.filled(hpr, fill_value=0.0)
    zpr = ma.filled(zpr, fill_value=0)

    for a in [xpr, ypr, hpr, zpr]:
        logger.info('Reduced shape of ... is {}'.format(a.shape))

    return xpr, ypr, hpr, zpr
