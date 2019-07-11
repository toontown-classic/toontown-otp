import ZoneUtil
import ToontownGlobals


def genDNAFileName(zoneId):
    zoneId = ZoneUtil.getCanonicalZoneId(zoneId)
    hoodId = ZoneUtil.getCanonicalHoodId(zoneId)
    hood = ToontownGlobals.dnaMap[hoodId]
    phase = ToontownGlobals.streetPhaseMap[hoodId]
    if hoodId == zoneId:
        zoneId = 'sz'

    return 'phase_%s/dna/%s_%s.pdna' % (phase, hood, zoneId)


def extractGroupName(groupFullName):
    return groupFullName.split(':', 1)[0]
