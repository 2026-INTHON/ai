"""Build front-view rigged 2.5D GLBs from one fixed reference-matched character sheet.

No image generation is performed. Texture pixels, identity, and outfits are deterministic.
Requires numpy and Pillow; exports standard glTF skinning, morph targets and animation clips.
"""
import argparse
import hashlib
import io
import json
import math
import struct
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PROFILES = {
    "girlfriend": {"name": "서윤", "role": "여자친구", "crop": [92, 110, 391, 979], "height": 1.65,
        "hip": [236, 505], "neck": [233, 280], "headBox": [151, 121, 311, 281], "faceBox": [177, 210, 299, 278],
        "eyes": [[201, 229], [255, 217]], "mouth": [231, 252],
        "shoulderL": [183, 315], "elbowL": [132, 420], "handL": [136, 373],
        "shoulderR": [295, 319], "elbowR": [317, 416], "handR": [290, 498],
        "facePolygon": [[177,216],[214,207],[236,207],[252,202],[273,198],[282,211],[291,203],[299,213],[294,237],[280,245],[268,263],[249,273],[226,269],[207,263],[188,251]],
        "hairPolygons": [[[160,218],[167,160],[198,128],[242,123],[276,140],[301,177],[311,250],[303,282],[281,261],[273,223],[267,199],[242,206],[213,208],[178,218]],[[164,217],[182,218],[177,306],[175,370],[164,418],[151,415],[160,344]],[[284,237],[308,227],[315,300],[330,357],[340,408],[329,429],[317,390],[299,311],[275,423],[258,432],[270,324]]],
        "protected": [[[207,261],[260,266],[260,299],[276,310],[250,336],[213,328],[204,304],[220,285]],[[176,420],[264,425],[271,453],[173,447]],[[116,319],[180,320],[179,393],[114,396]],[[269,483],[296,482],[308,510],[291,522]]],
        "floorCut": 890, "feet": [[[141,865],[235,865],[240,917],[237,946],[216,954],[147,951],[145,933]],[[274,867],[354,867],[356,915],[370,946],[370,967],[336,971],[302,958],[278,934]]],
        "longHair": [[137, 275, 184, 435], [258, 265, 340, 435]]},
    "friend": {"name": "민준", "role": "친구", "crop": [389, 26, 773, 982], "height": 1.80,
        "hip": [566, 601], "neck": [546, 211], "headBox": [441, 34, 613, 199], "faceBox": [477, 97, 610, 199],
        "eyes": [[505, 160], [561, 141]], "mouth": [543, 180],
        "shoulderL": [469, 260], "elbowL": [435, 401], "handL": [478, 350],
        "shoulderR": [626, 245], "elbowR": [688, 362], "handR": [675, 225],
        "facePolygon": [[477,144],[492,133],[491,110],[511,101],[526,135],[536,131],[556,128],[572,116],[582,132],[593,125],[608,129],[608,153],[593,164],[580,187],[557,198],[526,193],[505,184],[490,172],[479,168]],
        "hairPolygons": [[[440,135],[449,92],[478,57],[512,42],[555,34],[600,66],[616,112],[600,148],[583,140],[574,123],[550,136],[532,146],[517,127],[511,104],[491,108],[491,135],[477,151],[456,164]]],
        "protected": [[[531,188],[569,187],[578,225],[555,244],[528,229]],[[448,291],[492,284],[512,357],[484,381],[452,369]],[[632,169],[716,173],[715,228],[693,264],[652,264],[632,219]],[[621,270],[643,266],[649,407],[705,425],[722,508],[717,548],[679,566],[649,549]]],
        "floorCut": 900, "feet": [[[479,878],[549,878],[569,894],[578,931],[566,954],[485,958],[463,946],[465,922]],[[636,885],[704,886],[732,906],[754,939],[756,963],[733,976],[660,965],[626,945]]], "longHair": []},
    "manager": {"name": "한 부장", "role": "부장님", "crop": [776, 25, 1113, 982], "height": 1.78,
        "hip": [944, 606], "neck": [906, 211], "headBox": [814, 32, 994, 200], "faceBox": [834, 91, 979, 202],
        "eyes": [[876, 152], [940, 143]], "mouth": [910, 181],
        "shoulderL": [817, 269], "elbowL": [791, 414], "handL": [806, 370],
        "shoulderR": [1008, 268], "elbowR": [1040, 406], "handR": [980, 493],
        "facePolygon": [[834,142],[858,134],[865,119],[867,96],[886,91],[903,97],[913,132],[929,124],[943,120],[949,138],[968,135],[979,145],[972,168],[957,172],[949,189],[927,201],[898,201],[875,190],[858,179],[843,176],[833,160]],
        "hairPolygons": [[[813,123],[832,76],[856,49],[898,35],[936,31],[978,70],[994,116],[975,147],[951,143],[942,121],[917,137],[908,116],[898,96],[871,94],[862,125],[855,145],[835,146]]],
        "protected": [[[886,190],[932,190],[933,225],[911,240],[886,230]],[[780,315],[845,315],[846,382],[811,398],[782,383]],[[968,467],[990,476],[991,517],[980,518]],[[859,344],[908,344],[908,424],[859,424]],[[926,460],[966,460],[975,560],[923,560]]],
        "floorCut": 890, "feet": [[[841,867],[913,867],[938,904],[937,932],[913,944],[843,946],[814,935],[813,918],[829,899]],[[971,870],[1032,870],[1039,920],[1067,931],[1085,948],[1084,967],[1060,975],[1001,965],[978,947],[971,924]]], "longHair": []},
    "professor": {"name": "김 교수", "role": "교수님", "crop": [1121, 68, 1494, 985], "height": 1.70,
        "hip": [1302, 608], "neck": [1292, 239], "headBox": [1186, 77, 1380, 247], "faceBox": [1230, 119, 1358, 233],
        "eyes": [[1257, 184], [1309, 172]], "mouth": [1288, 211],
        "shoulderL": [1214, 277], "elbowL": [1183, 394], "handL": [1246, 369],
        "shoulderR": [1372, 281], "elbowR": [1383, 407], "handR": [1344, 363],
        "facePolygon": [[1231,175],[1247,155],[1266,126],[1279,122],[1303,149],[1327,165],[1339,164],[1357,176],[1352,198],[1335,205],[1325,220],[1304,232],[1279,230],[1255,219],[1239,204],[1229,191]],
        "hairPolygons": [[[1185,187],[1199,140],[1221,103],[1250,82],[1280,77],[1317,80],[1354,109],[1377,155],[1380,197],[1359,225],[1330,241],[1316,231],[1337,211],[1351,193],[1345,173],[1328,164],[1302,147],[1280,121],[1265,127],[1247,157],[1232,177],[1224,207],[1246,232],[1234,244],[1203,226],[1191,211]]],
        "protected": [[[1277,226],[1316,224],[1325,254],[1300,268],[1277,256]],[[1228,305],[1347,313],[1342,380],[1271,397],[1215,385],[1214,344]],[[1331,349],[1364,323],[1367,342],[1356,379],[1337,380]],[[1352,259],[1378,259],[1369,318],[1347,314]],[[1373,428],[1410,450],[1431,467],[1446,549],[1407,569],[1383,555]]],
        "floorCut": 914, "feet": [[[1242,886],[1303,885],[1320,911],[1316,934],[1289,946],[1232,950],[1213,938],[1211,924],[1227,908]],[[1381,896],[1420,899],[1441,924],[1467,943],[1474,968],[1453,978],[1412,969],[1387,944]]], "longHair": []},
}
TARGETS = ["blink", "smile", "frown", "browRaise", "browFurrow", "mouthOpen"]
CLIPS = ["idle", "talk", "happy", "confused", "sad", "angry", "nod", "shake", "greeting"]


def png_bytes(image):
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def foreground(image):
    """Flood only the neutral studio background; keep enclosed light clothing."""
    rgb = np.asarray(image.convert("RGB"))
    candidate = (rgb.min(axis=2) > 221) & ((rgb.max(axis=2).astype(int) - rgb.min(axis=2)) < 27)
    h, w = candidate.shape
    seen = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if candidate[y, x] and not seen[y, x]: seen[y, x] = True; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if candidate[y, x] and not seen[y, x]: seen[y, x] = True; q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= nx < w and 0 <= ny < h and candidate[ny,nx] and not seen[ny,nx]:
                seen[ny,nx] = True; q.append((nx,ny))
    alpha = Image.fromarray(np.uint8(~seen) * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.45))
    result = image.convert("RGBA")
    result.putalpha(alpha)
    return result


def retain_figure(image, seed):
    """Remove disconnected fragments of neighboring figures from the lineup crop."""
    alpha = np.asarray(image)[:,:,3].copy()
    solid = alpha>8
    ys,xs = np.nonzero(solid)
    index = np.argmin((xs-seed[0])**2+(ys-seed[1])**2)
    start = (int(xs[index]),int(ys[index]))
    visited = np.zeros(solid.shape,bool)
    visited[start[1],start[0]] = True
    queue = deque([start]); h,w = solid.shape
    while queue:
        x,y = queue.popleft()
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=nx<w and 0<=ny<h and solid[ny,nx] and not visited[ny,nx]:
                visited[ny,nx]=True;queue.append((nx,ny))
    keep = np.asarray(Image.fromarray(np.uint8(visited)*255).filter(ImageFilter.MaxFilter(3)))>0
    alpha[~keep]=0
    image.putalpha(Image.fromarray(alpha))
    return image


def rect_mask(shape, box):
    mask = np.zeros(shape, bool)
    x0,y0,x1,y1 = [int(x) for x in box]
    mask[max(0,y0):min(shape[0],y1), max(0,x0):min(shape[1],x1)] = True
    return mask


def polygon_mask(size, polygons, origin):
    mask = Image.new("L", size)
    draw = ImageDraw.Draw(mask)
    for polygon in polygons:
        draw.polygon([(int(x-origin[0]),int(y-origin[1])) for x,y in polygon], fill=255)
    return np.asarray(mask)>0


def segment_distance(points, a, b):
    delta = b-a
    t = np.clip(((points-a)*delta).sum(axis=1) / max(float((delta*delta).sum()), 1), 0, 1)
    return np.linalg.norm(points-(a+t[:,None]*delta), axis=1), t


class Glb:
    def __init__(self):
        self.doc = {"asset": {"version":"2.0", "generator":"Malo deterministic 2.5D rig builder"},
            "scene":0, "scenes":[{"nodes":[0]}], "nodes":[{"name":"MaloCharacter", "children":[]}],
            "bufferViews":[], "accessors":[], "materials":[], "meshes":[], "skins":[], "animations":[],
            "images":[], "textures":[], "samplers":[{"magFilter":9729,"minFilter":9987,"wrapS":33071,"wrapT":33071}],
            "extensionsUsed":["KHR_materials_unlit","KHR_materials_variants"],
            "extensions":{"KHR_materials_variants":{"variants":[{"name":n} for n in ["hair_original","hair_chestnut","hair_black","outfit_original","outfit_navy","outfit_olive"]]}}}
        self.binary = bytearray()

    def view(self, data, target=None):
        while len(self.binary)%4: self.binary.append(0)
        v = {"buffer":0,"byteOffset":len(self.binary),"byteLength":len(data)}
        if target: v["target"] = target
        self.doc["bufferViews"].append(v); self.binary.extend(data)
        return len(self.doc["bufferViews"])-1

    def accessor(self, values, kind, component=5126, target=None, bounds=False):
        dtype = {5126:"<f4",5125:"<u4",5123:"<u2"}[component]
        arr = np.asarray(values, dtype=dtype)
        count = len(arr)
        a = {"bufferView":self.view(arr.tobytes(), target),"componentType":component,"type":kind,"count":count}
        if bounds:
            v = arr.reshape(count,-1); a["min"] = v.min(axis=0).tolist(); a["max"] = v.max(axis=0).tolist()
        self.doc["accessors"].append(a)
        return len(self.doc["accessors"])-1

    def material(self, name, image):
        index = len(self.doc["images"])
        self.doc["images"].append({"name":name,"bufferView":self.view(png_bytes(image)),"mimeType":"image/png"})
        self.doc["textures"].append({"sampler":0,"source":index})
        self.doc["materials"].append({"name":name,"pbrMetallicRoughness":{"baseColorTexture":{"index":index},"metallicFactor":0,"roughnessFactor":1},
            "alphaMode":"BLEND","doubleSided":True,"extensions":{"KHR_materials_unlit":{}}})
        return len(self.doc["materials"])-1

    def animation(self, name, times, tracks):
        t = self.accessor(times,"SCALAR",bounds=True)
        animation = {"name":name,"samplers":[],"channels":[]}
        for node, path, values in tracks:
            kind = {"rotation":"VEC4","translation":"VEC3","scale":"VEC3","weights":"SCALAR"}[path]
            if path == "weights": values = np.asarray(values).reshape(-1)
            output = self.accessor(values,kind)
            sampler = len(animation["samplers"])
            animation["samplers"].append({"input":t,"output":output,"interpolation":"LINEAR"})
            animation["channels"].append({"sampler":sampler,"target":{"node":node,"path":path}})
        self.doc["animations"].append(animation)

    def write(self, path):
        self.doc["buffers"] = [{"byteLength":len(self.binary)}]
        encoded = json.dumps(self.doc,separators=(",",":"),ensure_ascii=False).encode()
        encoded += b" "*((-len(encoded))%4)
        binary = bytes(self.binary) + b"\0"*((-len(self.binary))%4)
        content = struct.pack("<III",0x46546c67,2,12+8+len(encoded)+8+len(binary))
        content += struct.pack("<II",len(encoded),0x4e4f534a)+encoded+struct.pack("<II",len(binary),0x004e4942)+binary
        path.write_bytes(content)


def recolor(image, mask, color):
    arr = np.asarray(image).copy()
    rgb = arr[:,:,:3].astype(float)/255
    luma = rgb@np.array([0.2126,0.7152,0.0722])
    target = np.array(color)/255
    target_luma = float(target@np.array([0.2126,0.7152,0.0722]))
    shaded = target[None,None,:] * (0.36+0.85*luma[:,:,None]) / max(0.45,target_luma*1.9)
    arr[mask,:3] = np.uint8(np.clip(shaded[mask],0,1)*255)
    return Image.fromarray(arr)


def quat(x=0,y=0,z=0):
    cx,sx,cy,sy,cz,sz = math.cos(x/2),math.sin(x/2),math.cos(y/2),math.sin(y/2),math.cos(z/2),math.sin(z/2)
    return [sx*cy*cz+cx*sy*sz,cx*sy*cz-sx*cy*sz,cx*cy*sz+sx*sy*cz,cx*cy*cz-sx*sy*sz]


def build_character(key, source, output):
    p = PROFILES[key]
    x0,y0,x1,y1 = p["crop"]
    image = foreground(source.crop((x0,y0,x1,y1)))
    image = retain_figure(image,(p["neck"][0]-x0,p["neck"][1]-y0))
    w,h = image.size; scale = p["height"]/h
    alpha_array = np.asarray(image)[:,:,3].copy()
    background_rgb = np.asarray(image)[:,:,:3].astype(int)
    feet = polygon_mask((w,h),p["feet"],(x0,y0))
    floor = np.arange(h)[:,None]+y0 >= p["floorCut"]
    neutral_shadow = (background_rgb.min(axis=2)>190) & (background_rgb.max(axis=2)-background_rgb.min(axis=2)<18)
    alpha_array[floor & ~feet & neutral_shadow] = 0
    image.putalpha(Image.fromarray(alpha_array))
    local = lambda value: np.array(value,dtype=float)-np.array([x0,y0])
    point = {k:local(p[k]) for k in ["hip","neck","shoulderL","elbowL","handL","shoulderR","elbowR","handR","mouth"]}
    eyes = [local(e) for e in p["eyes"]]
    face = np.array(p["faceBox"])-np.array([x0,y0,x0,y0]); head = np.array(p["headBox"])-np.array([x0,y0,x0,y0])
    rgb = np.asarray(image)[:,:,:3]; alpha = np.asarray(image)[:,:,3]
    face_mask = polygon_mask((w,h),[p["facePolygon"]],(x0,y0))
    protected = polygon_mask((w,h),p["protected"],(x0,y0)) | face_mask
    hair_mask = polygon_mask((w,h),p["hairPolygons"],(x0,y0)) & (alpha>30) & ~protected
    if key != "professor":
        hair_mask &= rgb.mean(axis=2) < 158  # Do not tint pale sleeves at the long-hair boundary.
    yy,xx = np.mgrid[:h,:w]
    outfit_mask = (yy>point["neck"][1]+12)&(yy<h-70)&~hair_mask&(alpha>30)
    for hand in (point["handL"],point["handR"]):
        outfit_mask &= ((xx-hand[0])/28)**2+((yy-hand[1])/38)**2>1
    outfit_mask &= ~protected
    originals = np.asarray(image)
    textures = [image, recolor(image,hair_mask,[112,69,43]),recolor(image,hair_mask,[30,32,37]),
        recolor(image,outfit_mask,[40,57,82]),recolor(image,outfit_mask,[83,98,69])]
    assert all(np.array_equal(np.asarray(t)[face_mask],originals[face_mask]) for t in textures), "Identity pixels changed"
    target_folder = output/key; target_folder.mkdir(parents=True,exist_ok=True)
    image.save(target_folder/"canonical.png")
    glb = Glb()
    material = [glb.material(n,t) for n,t in zip(["Original","HairChestnut","HairBlack","OutfitNavy","OutfitOlive"],textures)]
    center = w/2
    def world(v, z=0): return np.array([(v[0]-center)*scale,(h-v[1])*scale,z],dtype=float)
    shoulder = (point["shoulderL"]+point["shoulderR"])/2
    joints = [("Root",None,np.array([center,h])),("Hips",0,point["hip"]),("Spine",1,shoulder),("Head",2,point["neck"]),
        ("UpperArmL",2,point["shoulderL"]),("ForeArmL",4,point["elbowL"]),("HandL",5,point["handL"]),
        ("UpperArmR",2,point["shoulderR"]),("ForeArmR",7,point["elbowR"]),("HandR",8,point["handR"])]
    node_ids = []
    for index,(name,parent,position) in enumerate(joints):
        pos = world(position)
        if parent is not None: pos -= world(joints[parent][2])
        node_ids.append(len(glb.doc["nodes"]))
        glb.doc["nodes"].append({"name":name,"translation":pos.tolist()})
        parent_id = 0 if parent is None else node_ids[parent]
        glb.doc["nodes"][parent_id].setdefault("children",[]).append(node_ids[-1])
    inverse = []
    for _,_,pos in joints:
        matrix = np.eye(4); matrix[:3,3] = -world(pos); inverse.append(matrix.T.flatten())
    glb.doc["skins"].append({"name":"MaloFrontRig","joints":node_ids,"skeleton":node_ids[0],"inverseBindMatrices":glb.accessor(inverse,"MAT4")})
    xs = sorted(set(range(0,w,7))|set(range(max(0,int(head[0])-5),min(w,int(head[2])+5),3))|{w-1})
    ys = sorted(set(range(0,h,7))|set(range(max(0,int(face[1])-8),min(h,int(face[3])+8),2))|{h-1})
    points = np.array([[x,y] for y in ys for x in xs],dtype=float)
    n = len(points); px = points[:,0].astype(int); py = points[:,1].astype(int)
    positions = np.array([world(v) for v in points],np.float32)
    # A shallow relief, intended for the front and small view angles, not 360-degree inspection.
    bulge = np.sqrt(np.clip(1-((points[:,0]-center)/(w*.58))**2,0,1))
    positions[:,2] = .015+.055*bulge
    head_region = (points[:,0]>=head[0])&(points[:,0]<=head[2])&(points[:,1]>=head[1])&(points[:,1]<=head[3])
    positions[head_region,2] += .04*np.sin(np.clip((points[head_region,1]-head[1])/(head[3]-head[1]),0,1)*np.pi)
    uv = np.column_stack([points[:,0]/(w-1),points[:,1]/(h-1)]).astype(np.float32)
    normals = np.tile([0,0,1],(n,1)).astype(np.float32)
    weights = np.zeros((n,len(joints)))
    chest = np.clip((point["hip"][1]-points[:,1])/max(1,point["hip"][1]-shoulder[1]),0,1)
    weights[:,0] = 1-chest; weights[:,2] = chest
    for suffix,first,fore,hand in [("L",4,5,6),("R",7,8,9)]:
        a,b,c = point["shoulder"+suffix],point["elbow"+suffix],point["hand"+suffix]
        d,t = segment_distance(points,a,b)
        strength = np.clip(1-d/49,0,.87)
        weights *= (1-strength[:,None]); weights[:,first]+=strength*(1-t); weights[:,fore]+=strength*t
        d,t = segment_distance(points,b,c); strength=np.clip(1-d/33,0,.96)
        weights *= (1-strength[:,None]); weights[:,fore]+=strength*(1-t); weights[:,hand]+=strength*t
    # Blend through the neck and long hair; a hard rectangular seam would tear on a head tilt.
    neck_y = point["neck"][1]
    head_strength = np.where(head_region, np.clip((neck_y+12-points[:,1])/30,0,1), 0.)
    # Skinning must stay continuous: texture color masks would produce jagged moving edges.
    for box in p["longHair"]:
        bx0,by0,bx1,by1 = np.array(box)-np.array([x0,y0,x0,y0])
        width = max(1,(bx1-bx0)/2)
        taper = 1-np.clip((points[:,1]-neck_y)/max(1,by1-neck_y),0,1)
        strength = .6*taper*np.exp(-((points[:,0]-(bx0+bx1)/2)/width)**2)
        head_strength = np.maximum(head_strength,strength)
    weights *= 1-head_strength[:,None]
    weights[:,3] += head_strength
    palette = np.argsort(weights,axis=1)[:,-4:]
    influence = np.take_along_axis(weights,palette,axis=1)
    influence[influence<1e-7] = 0
    palette[influence==0] = 0
    influence /= np.maximum(influence.sum(axis=1,keepdims=True),1e-8)
    attrs = {"POSITION":glb.accessor(positions,"VEC3",target=34962,bounds=True),"NORMAL":glb.accessor(normals,"VEC3",target=34962),
        "TEXCOORD_0":glb.accessor(uv,"VEC2",target=34962),"JOINTS_0":glb.accessor(palette,"VEC4",5123,34962),
        "WEIGHTS_0":glb.accessor(influence,"VEC4",target=34962)}
    morphs = [np.zeros_like(positions) for _ in TARGETS]
    for eye in eyes:
        dx=(points[:,0]-eye[0])/21; dy=(points[:,1]-eye[1])/10
        g=np.exp(-dx*dx-dy*dy)
        morphs[0][:,1] += .94*(points[:,1]-eye[1])*g*scale
        brow_y=eye[1]-15; g2=np.exp(-((points[:,0]-eye[0])/23)**2-((points[:,1]-brow_y)/7)**2)
        morphs[3][:,1] += 6*g2*scale
        side=-1 if eye[0]<np.mean(eyes,axis=0)[0] else 1
        morphs[4][:,1] += (side*(points[:,0]-eye[0])*.22-2)*g2*scale
    mx,my=point["mouth"]; dx=points[:,0]-mx; dy=points[:,1]-my
    mouth=np.exp(-(dx/18)**2-(dy/9)**2)
    morphs[1][:,1] += (dx*dx/80-1)*mouth*scale
    morphs[2][:,1] -= (dx*dx/80-1)*mouth*scale
    morphs[5][:,1] -= dy*mouth*1.9*scale
    targets = [{"POSITION":glb.accessor(m,"VEC3",target=34962,bounds=True)} for m in morphs]
    groups = [[],[],[]]
    columns=len(xs)
    for yi in range(len(ys)-1):
        for xi in range(len(xs)-1):
            a=yi*columns+xi; b=a+1; c=a+columns; d=c+1
            if max(alpha[int(points[k,1]),int(points[k,0])] for k in (a,b,c,d)) < 4: continue
            sx=int((xs[xi]+xs[xi+1])/2); sy=int((ys[yi]+ys[yi+1])/2)
            kind=1 if hair_mask[sy,sx] else 2 if outfit_mask[sy,sx] else 0
            groups[kind].extend([a,c,b,b,c,d])
    mesh_nodes=[]
    for kind,name in enumerate(["FaceBodyProps","Hair","Outfit"]):
        primitive={"attributes":attrs,"indices":glb.accessor(groups[kind],"SCALAR",5125,34963),"material":material[0],"targets":targets}
        if kind:
            pairs=[(0,0),(1,1),(2,2)] if kind==1 else [(0,3),(3,4),(4,5)]
            primitive["extensions"]={"KHR_materials_variants":{"mappings":[{"material":m,"variants":[v]} for m,v in pairs]}}
        mesh=len(glb.doc["meshes"])
        glb.doc["meshes"].append({"name":name,"primitives":[primitive],"weights":[0]*len(TARGETS),"extras":{"targetNames":TARGETS}})
        node=len(glb.doc["nodes"]); mesh_nodes.append(node)
        glb.doc["nodes"].append({"name":name,"mesh":mesh,"skin":0,"weights":[0]*len(TARGETS)})
        glb.doc["scenes"][0]["nodes"].append(node)
    head_node=node_ids[3]; spine_node=node_ids[2]
    rest_head=np.array(glb.doc["nodes"][head_node]["translation"])
    for name in CLIPS:
        duration=4 if name=="idle" else 2.4
        times=np.linspace(0,duration,25)
        head_rot=[]; head_pos=[]; spine_scale=[]; face_weights=[]; hand_rot=[]
        for t in times:
            phase=t/duration; wave=math.sin(math.pi*phase); repeat=math.sin(4*math.pi*phase)
            rx=ry=rz=0.; shift=np.zeros(3); face_values=np.zeros(len(TARGETS))
            blink=math.exp(-((phase-.37)/.018)**2)+math.exp(-((phase-.85)/.018)**2)
            face_values[0]=min(1,blink)
            if name=="idle": rz=.012*math.sin(2*math.pi*phase)
            if name=="talk": face_values[5]=(.2+.8*abs(math.sin(10*math.pi*phase)))*wave; rz=.018*repeat
            if name=="happy": face_values[1]=.85*wave; face_values[0]=max(face_values[0],.35*wave); rx=.07*wave; shift[1]=-.012*wave
            if name=="confused": rz=.13*wave; face_values[3]=.85*wave
            if name=="sad": rz=-.065*wave; rx=.09*wave; shift[1]=-.02*wave; face_values[2]=.9*wave
            if name=="angry": face_values[4]=.95*wave; face_values[2]=.35*wave; ry=.035*repeat; shift[2]=.012*wave
            if name in ("nod","greeting"): rx=.11*abs(repeat)*wave; shift[1]=-.024*abs(repeat)*wave
            if name=="shake": ry=.09*repeat*wave; shift[0]=.018*repeat*wave
            head_rot.append(quat(rx,ry,rz)); head_pos.append(rest_head+shift)
            spine_scale.append([1,1+.005*math.sin(2*math.pi*phase),1]); face_weights.append(face_values)
            hand_rot.append(quat(z=.10*repeat*wave if name=="greeting" and key=="friend" else 0))
        tracks=[(head_node,"rotation",head_rot),(head_node,"translation",head_pos),(spine_node,"scale",spine_scale),(node_ids[9],"rotation",hand_rot)]
        tracks += [(node,"weights",face_weights) for node in mesh_nodes]
        glb.animation(name,times,tracks)
    identity=hashlib.sha256(originals[face_mask].tobytes()).hexdigest()
    glb.doc["nodes"][0]["extras"]={"characterId":key,"view":"front-2.5d","sourceIdentityHash":identity,"maxYawDegrees":8,
        "parts":["FaceBodyProps","Hair","Outfit"],"expressions":TARGETS,"animations":CLIPS}
    path=target_folder/(key+".glb"); glb.write(path)
    model_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata={"id":key,"name":p["name"],"role":p["role"],"height":p["height"],"modelUrl":f"./{key}/{key}.glb?v={model_hash[:12]}","modelSha256":model_hash,
        "canonicalUrl":f"./{key}/canonical.png","view":"front-2.5d","maxYawDegrees":8,"parts":["FaceBodyProps","Hair","Outfit"],
        "morphTargets":TARGETS,"animations":CLIPS,"sourceIdentityHash":identity,"vertices":n,"triangles":sum(map(len,groups))//3,
        "bytes":path.stat().st_size,"customization":{"hair":["original","chestnut","black"],"outfit":["original","navy","olive"]},
        "limitation":"Front-view relief mesh. Cosmetic presets currently change color, not haircut or garment silhouette."}
    (target_folder/"rig.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    return metadata


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    source=Image.open(args.source).convert("RGB")
    assert source.size==(1536,1024), "Landmarks are calibrated to the fixed 1536x1024 sheet"
    items=[build_character(key,source,args.out) for key in PROFILES]
    catalog={"format":"glTF 2.0 GLB","pipeline":"fixed-texture-skinned-2.5d","runtimeImageGeneration":False,
        "sourceSheetSha256":hashlib.sha256(args.source.read_bytes()).hexdigest(),"items":items}
    (args.out/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps([{k:m[k] for k in ("id","vertices","triangles","bytes")} for m in items]))


if __name__=="__main__": main()
