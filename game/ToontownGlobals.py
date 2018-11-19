from panda3d.core import *

MaxFriends = 50
FriendChat = 1
CommonChat = 1
SuperChat = 2

SPHidden = 0
SPRender = 1
SPDonaldsBoat = 2
SPMinniesPiano = 3
SPDynamic = 4

QuietZone = 1
UberZone = 2
DonaldsDock = 1000
ToontownCentral = 2000
TheBrrrgh = 3000
MinniesMelodyland = 4000
DaisyGardens = 5000
OutdoorZone = 6000
FunnyFarm = 7000
GoofySpeedway = 8000
DonaldsDreamland = 9000
BarnacleBoulevard = 1100
SeaweedStreet = 1200
LighthouseLane = 1300
SillyStreet = 2100
LoopyLane = 2200
PunchlinePlace = 2300
WalrusWay = 3100
SleetStreet = 3200
PolarPlace = 3300
AltoAvenue = 4100
BaritoneBoulevard = 4200
TenorTerrace = 4300
ElmStreet = 5100
MapleStreet = 5200
OakStreet = 5300
LullabyLane = 9100
PajamaPlace = 9200
ToonHall = 2513
HoodHierarchy = {ToontownCentral: (SillyStreet, LoopyLane, PunchlinePlace),
 DonaldsDock: (BarnacleBoulevard, SeaweedStreet, LighthouseLane),
 TheBrrrgh: (WalrusWay, SleetStreet, PolarPlace),
 MinniesMelodyland: (AltoAvenue, BaritoneBoulevard, TenorTerrace),
 DaisyGardens: (ElmStreet, MapleStreet, OakStreet),
 DonaldsDreamland: (LullabyLane, PajamaPlace),
 GoofySpeedway: ()}
WelcomeValleyToken = 0
BossbotHQ = 10000
BossbotLobby = 10100
BossbotCountryClubIntA = 10500
BossbotCountryClubIntB = 10600
BossbotCountryClubIntC = 10700
SellbotHQ = 11000
SellbotLobby = 11100
SellbotFactoryExt = 11200
SellbotFactoryInt = 11500
CashbotHQ = 12000
CashbotLobby = 12100
CashbotMintIntA = 12500
CashbotMintIntB = 12600
CashbotMintIntC = 12700
LawbotHQ = 13000
LawbotLobby = 13100
LawbotOfficeExt = 13200
LawbotOfficeInt = 13300
LawbotStageIntA = 13300
LawbotStageIntB = 13400
LawbotStageIntC = 13500
LawbotStageIntD = 13600
Tutorial = 15000
MyEstate = 16000
GolfZone = 17000
PartyHood = 18000
HoodsAlwaysVisited = [17000, 18000]
WelcomeValleyBegin = 22000
WelcomeValleyEnd = 61000
DynamicZonesBegin = 61000
DynamicZonesEnd = 1 << 20

RaceGameId = 1
CannonGameId = 2
TagGameId = 3
PatternGameId = 4
RingGameId = 5
MazeGameId = 6
TugOfWarGameId = 7
CatchGameId = 8

TrophyStarLevels = (10, 20, 30, 50, 75, 100)
TrophyStarColors = (Vec4(0.90000000000000002, 0.59999999999999998, 0.20000000000000001, 1), Vec4(0.90000000000000002, 0.59999999999999998, 0.20000000000000001, 1),
                    Vec4(0.80000000000000004, 0.80000000000000004, 0.80000000000000004, 1), Vec4(0.80000000000000004, 0.80000000000000004, 0.80000000000000004, 1),
                    Vec4(1, 1, 0, 1), Vec4(1, 1, 0, 1))


ToonForwardSpeed = 16.0
ToonReverseSpeed = 8.0
ToonRotateSpeed = 80.0
ToonForwardSlowSpeed = 6.0
ToonReverseSlowSpeed = 2.5
ToonRotateSlowSpeed = 33.0
MickeySpeed = 5.0
MinnieSpeed = 3.2000000000000002
DonaldSpeed = 3.6800000000000002
GoofySpeed = 5.2000000000000002
PlutoSpeed = 5.5
