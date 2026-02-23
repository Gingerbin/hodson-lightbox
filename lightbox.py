import pygame
import math
import sys
import json
import os
import random
from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum
from datetime import datetime

# Initialize Pygame
pygame.init()
pygame.font.init()
pygame.mixer.init()

# Constants - Fixed internal resolution (16:9)
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
CURVE_DEPTH = 45
SENSOR_RADIUS = 35
MAX_RAY_DISTANCE = 6000

# Colors
BG_COLOR = (15, 15, 25)
PANEL_COLOR = (30, 30, 45)
ACCENT_COLOR = (70, 130, 200)
HIGHLIGHT = (100, 200, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 80, 80)
GREEN = (80, 255, 120)
ORANGE = (255, 140, 0)
YELLOW = (255, 255, 100)
BLUE = (80, 150, 255)
VIOLET = (180, 100, 255)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)
BRONZE = (205, 127, 50)
GRAY = (120, 120, 130)
DARK_GRAY = (60, 60, 70)
LOCKED_COLOR = (80, 80, 90)

# Scoring
TIME_PENALTY = 30
MOVE_PENALTY = 200
ITEM_PENALTY = 400
MAX_SCORE = 10000

class ItemType(Enum):
    PLANE_MIRROR = "plane_mirror"
    TRIANGLE = "triangle"
    RECTANGLE = "rectangle"
    CURVED_MIRROR = "curved_mirror"
    CONCAVE_LENS = "concave_lens"
    CONVEX_LENS = "convex_lens"

@dataclass
class Material:
    ior_red: float = 1.50
    ior_orange: float = 1.515
    ior_yellow: float = 1.530
    ior_green: float = 1.545
    ior_blue: float = 1.560
    ior_violet: float = 1.575
    
    def get_ior(self, wavelength: str) -> float:
        iors = {
            "red": self.ior_red, "orange": self.ior_orange, "yellow": self.ior_yellow,
            "green": self.ior_green, "blue": self.ior_blue, "violet": self.ior_violet,
            "white": (self.ior_red + self.ior_violet) / 2
        }
        return iors.get(wavelength, 1.0)
    
    def set_base_ior(self, base: float):
        """Set all IORs based on a base red value, maintaining dispersion"""
        self.ior_red = base
        self.ior_orange = base + 0.025
        self.ior_yellow = base + 0.050
        self.ior_green = base + 0.075
        self.ior_blue = base + 0.100
        self.ior_violet = base + 0.125

AIR = Material(1.000, 1.000, 1.000, 1.000, 1.000, 1.000)
GLASS = Material(1.500, 1.525, 1.550, 1.575, 1.600, 1.625)

SPECTRUM = [
    ("red", RED, 1.50),
    ("orange", ORANGE, 1.515),
    ("yellow", YELLOW, 1.530),
    ("green", GREEN, 1.545),
    ("blue", BLUE, 1.560),
    ("violet", VIOLET, 1.575)
]

class Vector2:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
    
    def __add__(self, other): return Vector2(self.x + other.x, self.y + other.y)
    def __sub__(self, other): return Vector2(self.x - other.x, self.y - other.y)
    def __mul__(self, s: float): return Vector2(self.x * s, self.y * s)
    def dot(self, other): return self.x * other.x + self.y * other.y
    def length(self): return math.sqrt(self.x**2 + self.y**2)
    
    def normalize(self):
        l = self.length()
        return Vector2(self.x/l, self.y/l) if l > 0 else Vector2(0, 0)
    
    def rotate(self, angle: float):
        c, s = math.cos(angle), math.sin(angle)
        return Vector2(self.x*c - self.y*s, self.x*s + self.y*c)
    
    def perp(self): return Vector2(-self.y, self.x).normalize()
    def to_tuple(self): return (self.x, self.y)

class Ray:
    def __init__(self, pos: Vector2, dir: Vector2, color, wave: str, white=False, intensity=1.0):
        self.origin = pos
        self.direction = dir.normalize()
        self.color = color
        self.wavelength = wave
        self.is_white = white or wave == "white"
        self.path = [(pos.x, pos.y)]
        self.active = True
        self.bounces = 0
        self.material = AIR
        self.intensity = intensity
        self.distance_traveled = 0.0
    
    def get_endpoint(self):
        remaining = max(0, 1.0 - (self.distance_traveled / MAX_RAY_DISTANCE))
        max_dist = MAX_RAY_DISTANCE * remaining
        return self.origin + self.direction * min(2000, max_dist)

class Item:
    def __init__(self, item_type: ItemType, x: float, y: float, w: float, h: float, rot: float = 0):
        self.type = item_type
        self.pos = Vector2(x, y)
        self.width, self.height = w, h
        self.rotation = rot
        self.dragging = False
        self.rotating = False
        self.drag_offset = Vector2(0, 0)
        self.rotation_offset = 0
        self.update_shape()
    
    def update_shape(self):
        w, h = self.width, self.height
        rad = math.radians(self.rotation)
        
        if self.type == ItemType.TRIANGLE:
            r = w / 2
            pts = []
            for i in range(3):
                angle = math.radians(i * 120 - 90)
                pts.append(Vector2(r * math.cos(angle), r * math.sin(angle)))
        elif self.type == ItemType.RECTANGLE:
            pts = [Vector2(-w/2, -h/2), Vector2(w/2, -h/2), Vector2(w/2, h/2), Vector2(-w/2, h/2)]
        elif self.type == ItemType.CURVED_MIRROR:
            # Concave dish shape - opens UPWARD to catch light from above
            pts = []
            steps = 15
            for i in range(steps):
                t = i / (steps - 1)
                x = -w/2 + w * t
                y = CURVE_DEPTH * (1 - abs(2*t - 1))**2
                pts.append(Vector2(x, y))
        elif self.type == ItemType.PLANE_MIRROR:
            pts = [Vector2(-w/2, 0), Vector2(w/2, 0)]
        elif self.type == ItemType.CONCAVE_LENS:
            pts = []
            curve = w * 0.3
            steps = 6
            for i in range(steps):
                t = i / (steps - 1)
                x = -w/2 + w * t
                y = -h/2 + curve * (1 - (2*t - 1)**2)
                pts.append(Vector2(x, y))
            for i in range(steps):
                t = i / (steps - 1)
                x = w/2 - w * t
                y = h/2 - curve * (1 - (2*t - 1)**2)
                pts.append(Vector2(x, y))
        elif self.type == ItemType.CONVEX_LENS:
            pts = []
            bulge = h * 0.3
            steps = 6
            for i in range(steps):
                t = i / (steps - 1)
                x = -w/2 + w * t
                y = -h/2 - bulge * (1 - (2*t - 1)**2)
                pts.append(Vector2(x, y))
            for i in range(steps):
                t = i / (steps - 1)
                x = w/2 - w * t
                y = h/2 + bulge * (1 - (2*t - 1)**2)
                pts.append(Vector2(x, y))
        else:
            pts = []
        
        self.shape = [p.rotate(rad) + self.pos for p in pts]
    
    def get_segments(self):
        return [(self.shape[i], self.shape[(i+1) % len(self.shape)]) for i in range(len(self.shape))]
    
    def contains(self, pt: Vector2):
        return (pt - self.pos).length() < max(self.width, self.height) / 2
    
    def get_handle(self):
        rad = math.radians(self.rotation)
        return Vector2(self.width/2, -self.height/2).rotate(rad) + self.pos
    
    def constrain(self, sw: int, sh: int):
        m = 50
        self.pos.x = max(m, min(sw-m, self.pos.x))
        self.pos.y = max(m, min(sh-m, self.pos.y))
        self.update_shape()
    
    def draw(self, screen):
        if not self.shape:
            return
        
        pts = [(p.x, p.y) for p in self.shape]
        
        if self.type in [ItemType.PLANE_MIRROR, ItemType.CURVED_MIRROR]:
            pygame.draw.lines(screen, (200, 220, 240), False, pts, 4 if self.type == ItemType.PLANE_MIRROR else 3)
            pygame.draw.lines(screen, WHITE, False, pts, 2)
        else:
            s = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            if self.type in [ItemType.TRIANGLE, ItemType.RECTANGLE]:
                pygame.draw.polygon(s, (220, 240, 255, 120), pts)
                pygame.draw.polygon(s, (180, 220, 255, 255), pts, 2)
            else:
                pygame.draw.polygon(s, (200, 220, 255, 100), pts)
                pygame.draw.polygon(s, (150, 180, 220, 200), pts, 2)
            screen.blit(s, (0, 0))
        
        h = self.get_handle()
        pygame.draw.circle(screen, YELLOW, (int(h.x), int(h.y)), 8)
        pygame.draw.line(screen, (150, 150, 150), (self.pos.x, self.pos.y), (h.x, h.y), 1)
        pygame.draw.circle(screen, RED if self.dragging else WHITE, (int(self.pos.x), int(self.pos.y)), 4)

class LightBox:
    def __init__(self, x: float, y: float, angle: float = 0, lock_pos: bool = False, lock_rot: bool = False):
        self.pos = Vector2(x, y)
        self.angle = angle
        self.w, self.h = 80, 60
        self.dragging = False
        self.rotating = False
        self.offset = Vector2(0, 0)
        self.angle_offset = 0
        self.lock_pos = lock_pos
        self.lock_rot = lock_rot
    
    def get_dir(self):
        rad = math.radians(self.angle)
        return Vector2(math.cos(rad), math.sin(rad))
    
    def get_perp(self):
        rad = math.radians(self.angle)
        return Vector2(-math.sin(rad), math.cos(rad))
    
    def get_corner(self):
        rad = math.radians(self.angle)
        return Vector2(-self.w/2, -self.h/2).rotate(rad) + self.pos
    
    def contains(self, pt: Vector2):
        if self.lock_pos and self.lock_rot:
            return False
        local = pt - self.pos
        rad = math.radians(-self.angle)
        lx = local.x * math.cos(rad) - local.y * math.sin(rad)
        ly = local.x * math.sin(rad) + local.y * math.cos(rad)
        return abs(lx) < self.w/2 and abs(ly) < self.h/2
    
    def corner_contains(self, pt: Vector2):
        if self.lock_rot:
            return False
        return (pt - self.get_corner()).length() < 15
    
    def constrain(self, sw: int, sh: int):
        m = 60
        self.pos.x = max(m, min(sw-m, self.pos.x))
        self.pos.y = max(m, min(sh-m, self.pos.y))
    
    def draw(self, screen):
        rad = math.radians(self.angle)
        corners = []
        for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            off = Vector2(dx * self.w/2, dy * self.h/2).rotate(rad)
            corners.append((self.pos.x + off.x, self.pos.y + off.y))
        
        pygame.draw.polygon(screen, (40, 40, 50), corners)
        pygame.draw.polygon(screen, (200, 200, 220), corners, 2)
        
        emit = Vector2(self.w/2, 0).rotate(rad)
        pygame.draw.circle(screen, WHITE, (int(self.pos.x + emit.x), int(self.pos.y + emit.y)), 8)
        
        if not self.lock_rot:
            c = self.get_corner()
            pygame.draw.circle(screen, YELLOW, (int(c.x), int(c.y)), 8)
        
        f = pygame.font.SysFont('Arial', 14, True)
        t = f.render("LIGHT BOX", True, (220, 220, 240))
        r = t.get_rect(center=(self.pos.x, self.pos.y))
        screen.blit(t, r)

class Sensor:
    def __init__(self, x: float, y: float, color, tol: int = 40):
        self.pos = Vector2(x, y)
        self.radius = SENSOR_RADIUS
        self.color = color
        self.tol = tol
        self.active = False
        self.was_active = False
        self.is_white = (color == WHITE)
        self.pulse = 0
    
    def check_hit(self, ray: Ray):
        if len(ray.path) < 2 or ray.intensity < 0.2:
            return False
        
        for i in range(len(ray.path) - 1):
            p1 = Vector2(*ray.path[i])
            p2 = Vector2(*ray.path[i+1])
            line = p2 - p1
            len_sq = line.dot(line)
            if len_sq < 0.0001:
                continue
            
            t = max(0, min(1, (self.pos - p1).dot(line) / len_sq))
            closest = p1 + line * t
            if (self.pos - closest).length() < self.radius:
                return True
        return False
    
    def color_match(self, ray: Ray):
        if self.is_white:
            return ray.is_white
        if ray.is_white:
            return False
        return all(abs(ray.color[i] - self.color[i]) <= self.tol for i in range(3))
    
    def update(self, rays: List[Ray]):
        self.was_active = self.active
        self.active = False
        
        for ray in rays:
            if ray.intensity >= 0.2 and self.check_hit(ray) and self.color_match(ray):
                self.active = True
        
        if self.active:
            self.pulse = (self.pulse + 0.1) % (2 * math.pi)
        
        return self.active and not self.was_active
    
    def draw(self, screen):
        col = GREEN if self.active else RED
        w = 5 if self.active else 2
        
        if self.active:
            p = abs(math.sin(self.pulse)) * 8
            pygame.draw.circle(screen, col, (int(self.pos.x), int(self.pos.y)), int(self.radius + p), 2)
        
        pygame.draw.circle(screen, col, (int(self.pos.x), int(self.pos.y)), self.radius, w)
        
        s = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        a = 200 if self.active else 100
        pygame.draw.circle(s, (*self.color, a), (self.radius, self.radius), self.radius-4)
        screen.blit(s, (int(self.pos.x - self.radius), int(self.pos.y - self.radius)))
        
        if self.active:
            f = pygame.font.SysFont('Arial', 24, True)
            screen.blit(f.render("OK", True, WHITE), (int(self.pos.x) - 15, int(self.pos.y) - 12))
        
        f = pygame.font.SysFont('Arial', 13, True)
        name = "White" if self.is_white else ["Red", "Orange", "Yellow", "Green", "Blue", "Violet"][
            [RED, ORANGE, YELLOW, GREEN, BLUE, VIOLET].index(self.color) if self.color in [RED, ORANGE, YELLOW, GREEN, BLUE, VIOLET] else 0]
        screen.blit(f.render(name, True, WHITE), (int(self.pos.x) - 20, int(self.pos.y) - self.radius - 18))

class Physics:
    @staticmethod
    def intersect(p1, p2, p3, p4):
        d = (p1.x - p2.x) * (p3.y - p4.y) - (p1.y - p2.y) * (p3.x - p4.x)
        if abs(d) < 0.0001:
            return None
        
        t = ((p1.x - p3.x) * (p3.y - p4.y) - (p1.y - p3.y) * (p3.x - p4.x)) / d
        u = -((p1.x - p2.x) * (p1.y - p3.y) - (p1.y - p2.y) * (p1.x - p3.x)) / d
        
        if 0 <= t <= 1 and 0 <= u <= 1:
            pt = Vector2(p1.x + t * (p2.x - p1.x), p1.y + t * (p2.y - p1.y))
            return (pt, (pt - p1).length())
        return None
    
    @staticmethod
    def reflect(inc, n):
        inc, n = inc.normalize(), n.normalize()
        return (inc - n * (2 * inc.dot(n))).normalize()
    
    @staticmethod
    def refract(inc, n, n1, n2):
        inc, n = inc.normalize(), n.normalize()
        if n.dot(inc) > 0:
            n = Vector2(-n.x, -n.y)
        
        ratio = n1 / n2
        cos_i = -n.dot(inc)
        sin_t2 = ratio**2 * (1 - cos_i**2)
        
        if sin_t2 > 1:
            return None
        
        cos_t = math.sqrt(1 - sin_t2)
        return (inc * ratio + n * (ratio * cos_i - cos_t)).normalize()
    
    @staticmethod
    def normal(p1, p2):
        dx, dy = p2.x - p1.x, p2.y - p1.y
        l = math.sqrt(dx*dx + dy*dy)
        return Vector2(-dy/l, dx/l) if l > 0 else Vector2(0, 1)
    
    @staticmethod
    def fresnel_reflectance(incident, normal, n1, n2):
        incident = incident.normalize()
        normal = normal.normalize()
        
        cos_i = -normal.dot(incident)
        
        if n1 > n2:
            sin_t_sq = (n1 / n2) ** 2 * (1 - cos_i ** 2)
            if sin_t_sq > 1.0:
                return 1.0
        
        r0 = ((n1 - n2) / (n1 + n2)) ** 2
        return r0 + (1 - r0) * (1 - cos_i) ** 5

class Confetti:
    def __init__(self):
        self.particles = []
        self.active = False
    
    def burst(self, x, y, n=150):
        self.active = True
        for _ in range(n):
            self.particles.append({
                'pos': Vector2(x, y),
                'vel': Vector2(random.uniform(-5, 5), random.uniform(-12, -4)),
                'color': random.choice([RED, ORANGE, YELLOW, GREEN, BLUE, VIOLET, GOLD]),
                'size': random.randint(4, 10),
                'rot': random.randint(0, 360),
                'rot_spd': random.uniform(-5, 5)
            })
    
    def update(self):
        if not self.active:
            return
        
        for p in self.particles[:]:
            p['vel'].y += 0.3
            p['pos'] = p['pos'] + p['vel']
            p['rot'] += p['rot_spd']
            if p['pos'].y > SCREEN_HEIGHT + 50:
                self.particles.remove(p)
        
        if not self.particles:
            self.active = False
    
    def draw(self, screen):
        for p in self.particles:
            pts = []
            for i in range(4):
                a = math.radians(p['rot'] + i * 90)
                pts.append((p['pos'].x + p['size'] * math.cos(a), p['pos'].y + p['size'] * math.sin(a)))
            pygame.draw.polygon(screen, p['color'], pts)

class Level:
    def __init__(self, num: int):
        self.num = num
        self.sensors = []
        self.items = []
        self.box = LightBox(350, 400, 0)
        self.budget = 0
        self.setup()
    
    def setup(self):
        if self.num == 1:
            self.sensors = [Sensor(1000, 300, WHITE, 50)]
            self.budget = 1
            self.box = LightBox(350, 400, 0)
        elif self.num == 2:
            self.sensors = [Sensor(900, 250, WHITE, 50), Sensor(900, 550, WHITE, 50)]
            self.budget = 1
            self.box = LightBox(350, 400, 0)
        elif self.num == 3:
            self.sensors = [Sensor(1000, 300, RED, 40), Sensor(1000, 500, BLUE, 40)]
            self.budget = 1
            self.box = LightBox(350, 400, 0)
        elif self.num == 4:
            self.sensors = [Sensor(900, 200, RED, 35), Sensor(900, 320, ORANGE, 35),
                          Sensor(900, 440, YELLOW, 35), Sensor(900, 560, GREEN, 35), Sensor(900, 680, BLUE, 35)]
            self.budget = 2
            self.box = LightBox(350, 400, 0)
        elif self.num == 5:
            self.sensors = [Sensor(800, 250, YELLOW, 40), Sensor(800, 550, VIOLET, 40)]
            self.budget = 2
            self.box = LightBox(350, 400, 0)
        elif self.num == 6:
            self.sensors = [Sensor(800, 300, WHITE, 40), Sensor(800, 500, WHITE, 40),
                          Sensor(1000, 300, WHITE, 40), Sensor(1000, 500, WHITE, 40)]
            self.box = LightBox(450, 400, 45, True, False)
            self.budget = 2
        elif self.num == 7:
            self.sensors = [Sensor(300, 200, RED, 35), Sensor(900, 200, BLUE, 35),
                          Sensor(300, 600, VIOLET, 35), Sensor(900, 600, ORANGE, 35)]
            self.box = LightBox(600, 400, -90, True, False)
            self.budget = 3
        elif self.num == 8:
            cx, cy = 700, 400
            off = 150
            self.sensors = [Sensor(cx, cy-off, RED, 35), Sensor(cx+off, cy, YELLOW, 35),
                          Sensor(cx, cy+off, GREEN, 35), Sensor(cx-off, cy, BLUE, 35)]
            self.box = LightBox(350, 400, 0, True, True)
            self.budget = 3
        elif self.num == 9:
            self.sensors = [Sensor(600, 400, WHITE, 30), Sensor(400, 300, RED, 35),
                          Sensor(800, 300, BLUE, 35), Sensor(400, 500, GREEN, 35), Sensor(800, 500, VIOLET, 35)]
            self.box = LightBox(600, 100, 90, True, True)
            self.budget = 4
        elif self.num == 10:
            cx, cy = 600, 400
            r = 200
            cols = [RED, ORANGE, YELLOW, GREEN, BLUE]
            self.sensors = []
            for i, col in enumerate(cols):
                a = math.radians(90 + i * 72)
                self.sensors.append(Sensor(cx + r*math.cos(a), cy + r*math.sin(a), col, 30))
            self.sensors.append(Sensor(cx, cy, WHITE, 30))
            self.box = LightBox(350, 400, 0, True, True)
            self.budget = 5
    
    def all_active(self):
        return all(s.active for s in self.sensors)

class ScoreEntry:
    def __init__(self, name: str, score: int, level: int):
        self.name = name
        self.score = score
        self.level = level
        self.date = datetime.now().strftime("%Y-%m-%d")
    
    def to_dict(self):
        return {'name': self.name, 'score': self.score, 'level': self.level, 'date': self.date}
    
    @classmethod
    def from_dict(cls, d):
        e = cls(d['name'], d['score'], d['level'])
        e.date = d.get('date', '')
        return e

class Scoreboard:
    def __init__(self):
        self.scores = []
        self.load()
    
    def load(self):
        if os.path.exists('scores.json'):
            try:
                with open('scores.json', 'r') as f:
                    self.scores = [ScoreEntry.from_dict(d) for d in json.load(f)]
            except:
                pass
    
    def save(self):
        with open('scores.json', 'w') as f:
            json.dump([s.to_dict() for s in self.scores], f)
    
    def add(self, entry):
        self.scores.append(entry)
        self.scores.sort(key=lambda x: x.score, reverse=True)
        self.save()
        for i, s in enumerate(self.scores):
            if s is entry:
                return i + 1
        return 0
    
    def get_top(self, level, n=5):
        return [s for s in self.scores if s.level == level][:n]
    
    def get_best(self, level):
        filtered = [s for s in self.scores if s.level == level]
        return filtered[0] if filtered else None
    
    def clear(self):
        self.scores = []
        self.save()

class Shop:
    COSTS = {
        ItemType.PLANE_MIRROR: 0,
        ItemType.TRIANGLE: 3,
        ItemType.RECTANGLE: 3,
        ItemType.CURVED_MIRROR: 5,
        ItemType.CONCAVE_LENS: 8,
        ItemType.CONVEX_LENS: 8,
    }
    CUSTOM_REFRACTION_COST = 30
    
    def __init__(self):
        self.stars = 0
        self.unlocked = {t: False for t in ItemType}
        self.unlocked[ItemType.PLANE_MIRROR] = True
        self.completed = {}
        self.custom_refraction_unlocked = False
        self.custom_ior = 1.5
        self.load()
    
    def load(self):
        if os.path.exists('shop.json'):
            try:
                with open('shop.json', 'r') as f:
                    d = json.load(f)
                    self.stars = d.get('stars', 0)
                    self.completed = {int(k): v for k, v in d.get('completed', {}).items()}
                    for k, v in d.get('unlocked', {}).items():
                        try:
                            self.unlocked[ItemType(k)] = v
                        except:
                            pass
                    self.custom_refraction_unlocked = d.get('custom_refraction', False)
                    self.custom_ior = d.get('custom_ior', 1.5)
                    if self.custom_refraction_unlocked:
                        GLASS.set_base_ior(self.custom_ior)
                self.unlocked[ItemType.PLANE_MIRROR] = True
            except:
                pass
    
    def save(self):
        with open('shop.json', 'w') as f:
            json.dump({
                'stars': self.stars,
                'completed': self.completed,
                'unlocked': {k.value: v for k, v in self.unlocked.items()},
                'custom_refraction': self.custom_refraction_unlocked,
                'custom_ior': self.custom_ior
            }, f)
    
    def award(self, level: int, stars: int):
        bonus = 0
        message = None
        
        if level in self.completed:
            prev = self.completed[level]
            if stars > prev:
                bonus = stars - prev
                self.stars += bonus
                self.completed[level] = stars
                if bonus == 1:
                    message = f"Bonus star! Your skills have improved!"
                else:
                    message = f"Bonus {bonus} stars! Outstanding improvement!"
            elif stars == 3 and prev == 3:
                self.stars += 1
                bonus = 1
                message = "Perfection bonus! +1 star for mastery!"
        else:
            self.stars += stars
            self.completed[level] = stars
        
        self.save()
        return self.stars, bonus, message
    
    def unlock(self, item: ItemType):
        if self.unlocked[item]:
            return True
        cost = self.COSTS[item]
        if self.stars >= cost:
            self.stars -= cost
            self.unlocked[item] = True
            self.save()
            return True
        return False
    
    def unlock_custom_refraction(self):
        if self.custom_refraction_unlocked:
            return True
        if self.stars >= self.CUSTOM_REFRACTION_COST:
            self.stars -= self.CUSTOM_REFRACTION_COST
            self.custom_refraction_unlocked = True
            self.save()
            return True
        return False
    
    def update_ior(self, value: float):
        self.custom_ior = max(1.1, min(2.0, value))
        GLASS.set_base_ior(self.custom_ior)
        self.save()
    
    def is_level_unlocked(self, level_num: int):
        if level_num <= 1:
            return True
        return self.completed.get(level_num - 1, 0) >= 1
    
    def clear_all(self):
        self.stars = 0
        self.unlocked = {t: False for t in ItemType}
        self.unlocked[ItemType.PLANE_MIRROR] = True
        self.completed = {}
        self.custom_refraction_unlocked = False
        self.custom_ior = 1.5
        GLASS.set_base_ior(1.5)
        self.save()

class MenuBackground:
    def __init__(self, screen_width, screen_height):
        self.sw = screen_width
        self.sh = screen_height
        self.box = {
            'pos': Vector2(150, screen_height // 2),
            'angle': 0,
            'w': 80,
            'h': 60
        }
        self.prism = {
            'pos': Vector2(screen_width // 2, screen_height // 2),
            'rotation': 0,
            'rot_speed': 0.5,
            'size': 100
        }
        self.rays = []
    
    def update(self):
        self.prism['rotation'] += self.prism['rot_speed']
        self._trace_rays()
    
    def _get_prism_segments(self):
        cx, cy = self.prism['pos'].x, self.prism['pos'].y
        r = self.prism['size'] / 2
        pts = []
        for i in range(3):
            angle = math.radians(i * 120 + self.prism['rotation'] - 90)
            pts.append(Vector2(cx + r * math.cos(angle), cy + r * math.sin(angle)))
        
        segments = []
        for i in range(3):
            segments.append((pts[i], pts[(i+1)%3]))
        return segments
    
    def _trace_rays(self):
        self.rays = []
        box = self.box
        rad = math.radians(box['angle'])
        base_dir = Vector2(math.cos(rad), math.sin(rad))
        perp = Vector2(-math.sin(rad), math.cos(rad))
        origin = box['pos']
        
        prism_segs = self._get_prism_segments()
        
        for i in range(-1, 2):
            offset = perp * (i * 15)
            ray_origin = origin + offset
            
            best_dist = float('inf')
            best_pt = None
            best_normal = None
            
            for p1, p2 in prism_segs:
                hit = Physics.intersect(ray_origin, ray_origin + base_dir * 2000, p1, p2)
                if hit and hit[1] < best_dist:
                    best_dist = hit[1]
                    best_pt = hit[0]
                    n = Physics.normal(p1, p2)
                    if n.dot(base_dir) > 0:
                        n = Vector2(-n.x, -n.y)
                    best_normal = n
            
            if best_pt:
                self.rays.append({
                    'points': [(ray_origin.x, ray_origin.y), (best_pt.x, best_pt.y)],
                    'color': WHITE,
                    'width': 3,
                    'alpha': 255
                })
                
                dispersed_rays = []
                for cname, ccol, ior in SPECTRUM:
                    n1, n2 = AIR.get_ior(cname), GLASS.get_ior(cname)
                    refracted = Physics.refract(base_dir, best_normal, n1, n2)
                    
                    if refracted:
                        exit_pt = None
                        exit_normal = None
                        current = best_pt + refracted * 0.1
                        
                        for p1, p2 in prism_segs:
                            hit = Physics.intersect(current, current + refracted * 500, p1, p2)
                            if hit and hit[1] > 0.01:
                                exit_pt = hit[0]
                                n = Physics.normal(p1, p2)
                                if n.dot(refracted) > 0:
                                    n = Vector2(-n.x, -n.y)
                                exit_normal = n
                                break
                        
                        if exit_pt:
                            dispersed_rays.append({
                                'points': [(best_pt.x, best_pt.y), (exit_pt.x, exit_pt.y)],
                                'color': ccol,
                                'width': 2,
                                'alpha': 150
                            })
                            
                            n1, n2 = GLASS.get_ior(cname), AIR.get_ior(cname)
                            exited = Physics.refract(refracted, exit_normal, n1, n2)
                            
                            if exited:
                                end_pt = exit_pt + exited * 400
                                dispersed_rays.append({
                                    'points': [(exit_pt.x, exit_pt.y), (end_pt.x, end_pt.y)],
                                    'color': ccol,
                                    'width': 3,
                                    'alpha': 200
                                })
                
                self.rays.extend(dispersed_rays)
            else:
                end = ray_origin + base_dir * 400
                self.rays.append({
                    'points': [(ray_origin.x, ray_origin.y), (end.x, end.y)],
                    'color': WHITE,
                    'width': 2,
                    'alpha': 200
                })
    
    def draw(self, screen):
        w, h = screen.get_size()
        
        for ray in self.rays:
            if len(ray['points']) > 1:
                if ray.get('alpha', 255) < 255:
                    s = pygame.Surface((w, h), pygame.SRCALPHA)
                    col = (*ray['color'], ray['alpha'])
                    pygame.draw.lines(s, col, False, ray['points'], ray['width'])
                    screen.blit(s, (0, 0))
                else:
                    pygame.draw.lines(screen, ray['color'], False, ray['points'], ray['width'])
        
        box = self.box
        rad = math.radians(box['angle'])
        corners = []
        for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            off = Vector2(dx * box['w']/2, dy * box['h']/2).rotate(rad)
            corners.append((box['pos'].x + off.x, box['pos'].y + off.y))
        
        pygame.draw.polygon(screen, (50, 50, 60), corners)
        pygame.draw.polygon(screen, (200, 200, 220), corners, 2)
        emit = Vector2(box['w']/2, 0).rotate(rad)
        pygame.draw.circle(screen, WHITE, (int(box['pos'].x + emit.x), int(box['pos'].y + emit.y)), 6)
        
        cx, cy = self.prism['pos'].x, self.prism['pos'].y
        r = self.prism['size'] / 2
        pts = []
        for i in range(3):
            angle = math.radians(i * 120 + self.prism['rotation'] - 90)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(s, (200, 220, 255, 100), pts)
        pygame.draw.polygon(s, (180, 210, 255, 200), pts, 2)
        screen.blit(s, (0, 0))

class Game:
    def __init__(self):
        # Start in 1280x720 (16:9) with SCALED flag for automatic aspect ratio preservation
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE | pygame.SCALED)
        pygame.display.set_caption("Hodson Light Box")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 24)
        self.small = pygame.font.SysFont('Arial', 16)
        self.big = pygame.font.SysFont('Arial', 36, True)
        self.huge = pygame.font.SysFont('Arial', 72, True)
        
        try:
            self.bing = pygame.mixer.Sound('bing.mp3')
        except:
            self.bing = None
        
        self.state = "menu"
        self.level_num = 1
        self.level = None
        self.items = []
        self.rays = []
        self.dragged = None
        
        self.start_time = 0
        self.moves = 0
        self.items_used = 0
        self.countdown = 3
        self.countdown_start = 0
        
        self.name = ""
        self.last_name = ""
        self.final_score = 0
        self.position = 0
        self.stars_earned = 0
        self.bonus_message = None
        
        self.scoreboard = Scoreboard()
        self.shop = Shop()
        self.confetti = Confetti()
        # Use fixed dimensions for background
        self.menu_bg = MenuBackground(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.viewing_level = 1
        self.show_scores = False
        self.confirm_clear = False
        
        self.ior_dragging = False
        self.is_fullscreen = False
        
        self.update_rects()
    
    def update_rects(self):
        # Use fixed virtual resolution (1280x720) for all positioning
        # This ensures UI stays in place and just scales up/down
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        self.menu_btn = pygame.Rect(50, h - 80, 140, 40)
        
        self.lvl_btns = []
        btn_w, btn_h = 100, 100
        margin = 20
        cols = 5
        start_x = (w - (cols * (btn_w + margin))) // 2
        start_y = 180
        
        for i in range(10):
            row, col = divmod(i, cols)
            x = start_x + col * (btn_w + margin)
            y = start_y + row * (btn_h + margin + 20)
            self.lvl_btns.append(pygame.Rect(x, y, btn_w, btn_h))
        
        self.settings_btn = pygame.Rect(w - 150, 20, 130, 40)
        self.shop_btn = pygame.Rect(w - 150, 80, 130, 40)
        
        self.ior_slider_rect = pygame.Rect(30, 480, 180, 50)
        self.ior_track_rect = pygame.Rect(40, 505, 160, 4)
    
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            # Fullscreen with SCALED maintains aspect ratio (adds black bars if needed)
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.SCALED)
        else:
            # Return to windowed 1280x720
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE | pygame.SCALED)
    
    def start_level(self, n: int):
        if not self.shop.is_level_unlocked(n):
            return
        
        self.level_num = n
        self.level = Level(n)
        self.items = []
        self.rays = []
        self.state = "playing"
        self.start_time = pygame.time.get_ticks()
        self.moves = 0
        self.items_used = 0
        self.countdown = 3
        self.name = self.last_name
        self.bonus_message = None
    
    def calc_score(self):
        if not self.level:
            return 0
        time = (pygame.time.get_ticks() - self.start_time) / 1000
        return max(0, MAX_SCORE - int(time * TIME_PENALTY) - self.moves * MOVE_PENALTY - self.items_used * ITEM_PENALTY)
    
    def get_stars(self, score: int):
        base = MAX_SCORE - self.level_num * 500
        if score >= base * 0.9: return 3
        if score >= base * 0.75: return 2
        if score >= base * 0.5: return 1
        return 0
    
    def spawn(self, t: ItemType):
        if not self.level or self.level.budget <= 0 or not self.shop.unlocked.get(t, False):
            return False
        
        w, h = 100, 80
        if t in [ItemType.PLANE_MIRROR, ItemType.CURVED_MIRROR]:
            w, h = 120, 20
        
        self.items.append(Item(t, 600, 400, w, h))
        self.level.budget -= 1
        self.items_used += 1
        self.moves += 1
        return True
    
    def remove(self, item: Item):
        if item in self.items:
            self.items.remove(item)
            self.level.budget += 1
            self.moves += 1
    
    def get_intensity_at_distance(self, distance):
        return max(0.0, 1.0 - (distance / MAX_RAY_DISTANCE))
    
    def trace(self, ray: Ray):
        for _ in range(20):
            if not ray.active or ray.bounces >= 10:
                break
            
            if ray.distance_traveled >= MAX_RAY_DISTANCE:
                ray.active = False
                break
            
            best_dist = float('inf')
            best_pt = None
            best_n = None
            best_item = None
            
            for item in self.items:
                for s in item.get_segments():
                    hit = Physics.intersect(ray.origin, ray.get_endpoint(), s[0], s[1])
                    if hit and 0.1 < hit[1] < best_dist:
                        best_dist = hit[1]
                        best_pt = hit[0]
                        n = Physics.normal(s[0], s[1])
                        if n.dot(ray.direction) > 0:
                            n = Vector2(-n.x, -n.y)
                        best_n = n
                        best_item = item
            
            if best_pt:
                ray.path.append((best_pt.x, best_pt.y))
                ray.distance_traveled += best_dist
                ray.origin = best_pt
                
                current_intensity = self.get_intensity_at_distance(ray.distance_traveled)
                if current_intensity <= 0.01:
                    ray.active = False
                    break
                
                if best_item.type in [ItemType.PLANE_MIRROR, ItemType.CURVED_MIRROR]:
                    ray.direction = Physics.reflect(ray.direction, best_n)
                    ray.bounces += 1
                elif best_item.type in [ItemType.TRIANGLE, ItemType.RECTANGLE]:
                    entering = best_n.dot(best_item.pos - best_pt) < 0
                    
                    if ray.is_white:
                        n1 = ray.material.get_ior("white")
                        n2 = GLASS.get_ior("white")
                    else:
                        n1 = ray.material.get_ior(ray.wavelength)
                        n2 = GLASS.get_ior(ray.wavelength) if entering else AIR.get_ior(ray.wavelength)
                    
                    R = Physics.fresnel_reflectance(ray.direction, best_n, n1, n2)
                    T = 1.0 - R
                    
                    if R > 0.01 and ray.intensity * R > 0.01:
                        refl_dir = Physics.reflect(ray.direction, best_n)
                        refl_ray = Ray(Vector2(best_pt.x, best_pt.y), refl_dir, ray.color, ray.wavelength, ray.is_white, ray.intensity * R)
                        refl_ray.distance_traveled = ray.distance_traveled
                        refl_ray.bounces = ray.bounces + 1
                        self.rays.append(refl_ray)
                        self.trace(refl_ray)
                    
                    if T > 0.01 and ray.intensity * T > 0.01:
                        if ray.is_white and entering:
                            ray.active = False
                            for cname, ccol, ior in SPECTRUM:
                                n1_c = AIR.get_ior(cname)
                                n2_c = GLASS.get_ior(cname)
                                new_dir = Physics.refract(ray.direction, best_n, n1_c, n2_c)
                                if new_dir:
                                    new_ray = Ray(Vector2(best_pt.x, best_pt.y), new_dir, ccol, cname, False, ray.intensity * T)
                                    new_ray.material = GLASS
                                    new_ray.distance_traveled = ray.distance_traveled
                                    new_ray.bounces = ray.bounces + 1
                                    self.trace_color(new_ray)
                                    self.rays.append(new_ray)
                            return
                        else:
                            next_mat = GLASS if (ray.material == AIR and entering) else AIR
                            new_dir = Physics.refract(ray.direction, best_n, n1, n2)
                            if new_dir:
                                ray.direction = new_dir
                                ray.material = next_mat
                                ray.intensity *= T
                                ray.bounces += 1
                            else:
                                ray.active = False
                                return
                    else:
                        ray.active = False
                        return
                else:
                    entering = best_n.dot(best_item.pos - best_pt) < 0
                    
                    if ray.is_white and entering:
                        n1 = AIR.get_ior("white")
                        n2 = GLASS.get_ior("white")
                        R = Physics.fresnel_reflectance(ray.direction, best_n, n1, n2)
                        T = 1.0 - R
                        
                        if R > 0.01:
                            refl_dir = Physics.reflect(ray.direction, best_n)
                            refl_ray = Ray(Vector2(best_pt.x, best_pt.y), refl_dir, WHITE, "white", True, ray.intensity * R)
                            refl_ray.distance_traveled = ray.distance_traveled
                            refl_ray.bounces = ray.bounces + 1
                            self.rays.append(refl_ray)
                            self.trace(refl_ray)
                        
                        if T > 0.01:
                            ray.active = False
                            for cname, ccol, ior in SPECTRUM:
                                n1_c = AIR.get_ior(cname)
                                n2_c = GLASS.get_ior(cname)
                                new_dir = Physics.refract(ray.direction, best_n, n1_c, n2_c)
                                if new_dir:
                                    new_ray = Ray(Vector2(best_pt.x, best_pt.y), new_dir, ccol, cname, False, ray.intensity * T)
                                    new_ray.material = GLASS
                                    new_ray.distance_traveled = ray.distance_traveled
                                    new_ray.bounces = ray.bounces + 1
                                    self.trace_color(new_ray)
                                    self.rays.append(new_ray)
                        return
                    else:
                        if ray.material == GLASS and not entering:
                            n1, n2 = GLASS.get_ior(ray.wavelength), AIR.get_ior(ray.wavelength)
                        elif entering:
                            n1, n2 = AIR.get_ior(ray.wavelength), GLASS.get_ior(ray.wavelength)
                            ray.material = GLASS
                        else:
                            n1, n2 = GLASS.get_ior(ray.wavelength), AIR.get_ior(ray.wavelength)
                            ray.material = AIR
                        
                        R = Physics.fresnel_reflectance(ray.direction, best_n, n1, n2)
                        T = 1.0 - R
                        
                        if R > 0.01:
                            refl_dir = Physics.reflect(ray.direction, best_n)
                            refl_ray = Ray(Vector2(best_pt.x, best_pt.y), refl_dir, ray.color, ray.wavelength, False, ray.intensity * R)
                            refl_ray.distance_traveled = ray.distance_traveled
                            refl_ray.bounces = ray.bounces + 1
                            self.rays.append(refl_ray)
                            self.trace_color(refl_ray)
                        
                        if T > 0.01:
                            new_dir = Physics.refract(ray.direction, best_n, n1, n2)
                            if new_dir:
                                ray.direction = new_dir
                                ray.intensity *= T
                                ray.bounces += 1
                            else:
                                ray.active = False
                                return
                        else:
                            ray.active = False
                            return
            else:
                end = ray.origin + ray.direction * 2000
                segment_length = 2000
                ray.distance_traveled += segment_length
                
                if ray.distance_traveled >= MAX_RAY_DISTANCE:
                    remaining = MAX_RAY_DISTANCE - (ray.distance_traveled - segment_length)
                    if remaining > 0:
                        end = ray.origin + ray.direction * remaining
                        ray.path.append((end.x, end.y))
                    ray.active = False
                else:
                    ray.path.append((end.x, end.y))
                    ray.active = False
    
    def trace_color(self, ray: Ray):
        for _ in range(10):
            if not ray.active or ray.bounces >= 10:
                break
            
            if ray.distance_traveled >= MAX_RAY_DISTANCE:
                ray.active = False
                break
            
            best_dist = float('inf')
            best_pt = None
            best_n = None
            best_item = None
            
            for item in self.items:
                for s in item.get_segments():
                    hit = Physics.intersect(ray.origin, ray.get_endpoint(), s[0], s[1])
                    if hit and 1.0 < hit[1] < best_dist:
                        best_dist = hit[1]
                        best_pt = hit[0]
                        n = Physics.normal(s[0], s[1])
                        if n.dot(ray.direction) > 0:
                            n = Vector2(-n.x, -n.y)
                        best_n = n
                        best_item = item
            
            if best_pt:
                ray.path.append((best_pt.x, best_pt.y))
                ray.distance_traveled += best_dist
                ray.origin = best_pt
                
                if best_item.type in [ItemType.PLANE_MIRROR, ItemType.CURVED_MIRROR]:
                    ray.direction = Physics.reflect(ray.direction, best_n)
                    ray.bounces += 1
                elif best_item.type in [ItemType.TRIANGLE, ItemType.RECTANGLE]:
                    entering = best_n.dot(best_item.pos - best_pt) < 0
                    
                    n1 = ray.material.get_ior(ray.wavelength)
                    n2 = GLASS.get_ior(ray.wavelength) if entering else AIR.get_ior(ray.wavelength)
                    
                    R = Physics.fresnel_reflectance(ray.direction, best_n, n1, n2)
                    T = 1.0 - R
                    
                    if R > 0.01:
                        refl_dir = Physics.reflect(ray.direction, best_n)
                        refl_ray = Ray(Vector2(best_pt.x, best_pt.y), refl_dir, ray.color, ray.wavelength, False, ray.intensity * R)
                        refl_ray.distance_traveled = ray.distance_traveled
                        refl_ray.bounces = ray.bounces + 1
                        self.rays.append(refl_ray)
                        self.trace_color(refl_ray)
                    
                    if T > 0.01:
                        new_dir = Physics.refract(ray.direction, best_n, n1, n2)
                        if new_dir:
                            ray.direction = new_dir
                            ray.intensity *= T
                            ray.material = GLASS if (ray.material == AIR and entering) else AIR
                            ray.bounces += 1
                        else:
                            ray.active = False
                            return
                    else:
                        ray.active = False
                        return
                else:
                    entering = best_n.dot(best_item.pos - best_pt) < 0
                    
                    if ray.material == GLASS and not entering:
                        n1, n2 = GLASS.get_ior(ray.wavelength), AIR.get_ior(ray.wavelength)
                    elif entering:
                        n1, n2 = AIR.get_ior(ray.wavelength), GLASS.get_ior(ray.wavelength)
                    else:
                        n1, n2 = GLASS.get_ior(ray.wavelength), AIR.get_ior(ray.wavelength)
                    
                    R = Physics.fresnel_reflectance(ray.direction, best_n, n1, n2)
                    T = 1.0 - R
                    
                    if R > 0.01:
                        refl_dir = Physics.reflect(ray.direction, best_n)
                        refl_ray = Ray(Vector2(best_pt.x, best_pt.y), refl_dir, ray.color, ray.wavelength, False, ray.intensity * R)
                        refl_ray.distance_traveled = ray.distance_traveled
                        refl_ray.bounces = ray.bounces + 1
                        self.rays.append(refl_ray)
                        self.trace_color(refl_ray)
                    
                    if T > 0.01:
                        new_dir = Physics.refract(ray.direction, best_n, n1, n2)
                        if new_dir:
                            ray.direction = new_dir
                            ray.intensity *= T
                            ray.material = GLASS if (ray.material == AIR and entering) else AIR
                            ray.bounces += 1
                        else:
                            ray.active = False
                            return
                    else:
                        ray.active = False
                        return
            else:
                end = ray.origin + ray.direction * 2000
                ray.distance_traveled += 2000
                
                if ray.distance_traveled >= MAX_RAY_DISTANCE:
                    remaining = MAX_RAY_DISTANCE - (ray.distance_traveled - 2000)
                    if remaining > 0:
                        end = ray.origin + ray.direction * remaining
                        ray.path.append((end.x, end.y))
                    ray.active = False
                else:
                    ray.path.append((end.x, end.y))
                    ray.active = False
                break
    
    def update(self):
        # Always use fixed dimensions for logic
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        
        if self.state == "menu":
            self.menu_bg.update()
        
        if self.state == "playing" and self.level:
            self.rays = []
            perp = self.level.box.get_perp()
            for i in range(-1, 2):
                off = perp * (i * 12)
                r = Ray(self.level.box.pos + off, self.level.box.get_dir(), WHITE, "white", white=True)
                self.trace(r)
                self.rays.append(r)
            
            all_active = True
            just_activated = False
            for s in self.level.sensors:
                if s.update(self.rays):
                    just_activated = True
                if not s.active:
                    all_active = False
            
            if just_activated and self.bing:
                self.bing.play()
            
            if all_active:
                self.state = "countdown"
                self.countdown_start = pygame.time.get_ticks()
        
        elif self.state == "countdown":
            if not all(s.active for s in self.level.sensors):
                self.state = "playing"
                return
            
            elapsed = (pygame.time.get_ticks() - self.countdown_start) / 1000
            self.countdown = 3 - int(elapsed)
            
            self.rays = []
            perp = self.level.box.get_perp()
            for i in range(-1, 2):
                off = perp * (i * 12)
                r = Ray(self.level.box.pos + off, self.level.box.get_dir(), WHITE, "white", white=True)
                self.trace(r)
                self.rays.append(r)
            for s in self.level.sensors:
                s.update(self.rays)
            
            if self.countdown <= 0:
                self.final_score = self.calc_score()
                self.state = "complete"
                if not self.name:
                    self.name = self.last_name
        
        self.confetti.update()
    
    def draw_star(self, screen, x, y, size, fill=True):
        pts = []
        for i in range(10):
            a = math.radians(i * 36 - 90)
            r = size if i % 2 == 0 else size // 2
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        col = GOLD if fill else (80, 80, 80)
        pygame.draw.polygon(screen, col, pts)
        if not fill:
            pygame.draw.polygon(screen, GOLD, pts, 2)
    
    def draw_lock(self, screen, x, y, size):
        body = pygame.Rect(x - size//2, y, size, size)
        pygame.draw.rect(screen, LOCKED_COLOR, body, border_radius=3)
        pygame.draw.rect(screen, WHITE, body, 2, border_radius=3)
        arc = pygame.Rect(x - size//3, y - size//2, size//1.5, size)
        pygame.draw.arc(screen, LOCKED_COLOR, arc, 0, math.pi, 3)
    
    def draw_trophy(self, screen, x, y, size):
        cup = pygame.Rect(x - size//2, y - size//3, size, size//1.5)
        pygame.draw.ellipse(screen, GOLD, cup)
        pygame.draw.ellipse(screen, (200, 170, 0), cup, 2)
        pygame.draw.arc(screen, GOLD, (x - size, y - size//3, size//2, size//2), 0, math.pi, 3)
        pygame.draw.arc(screen, GOLD, (x + size//2, y - size//3, size//2, size//2), 0, math.pi, 3)
        pygame.draw.rect(screen, GOLD, (x - 3, y + size//6, 6, size//3))
        base = pygame.Rect(x - size//3, y + size//2, size//1.5, size//4)
        pygame.draw.rect(screen, GOLD, base, border_radius=2)
    
    def draw_ior_slider(self):
        screen = self.screen
        if self.shop.custom_refraction_unlocked:
            pygame.draw.rect(screen, PANEL_COLOR, self.ior_slider_rect, border_radius=5)
            pygame.draw.rect(screen, ACCENT_COLOR, self.ior_slider_rect, 2, border_radius=5)
            pygame.draw.rect(screen, DARK_GRAY, self.ior_track_rect, border_radius=2)
            t = (self.shop.custom_ior - 1.1) / 0.9
            handle_x = self.ior_track_rect.x + t * self.ior_track_rect.width
            pygame.draw.circle(screen, HIGHLIGHT, (int(handle_x), self.ior_track_rect.centery), 8)
            txt = self.small.render(f"IOR: {self.shop.custom_ior:.2f}", True, WHITE)
            screen.blit(txt, (self.ior_slider_rect.x + 10, self.ior_slider_rect.y + 5))
            screen.blit(self.small.render("1.1", True, GRAY), (self.ior_track_rect.x, self.ior_track_rect.y + 10))
            screen.blit(self.small.render("2.0", True, GRAY), (self.ior_track_rect.right - 20, self.ior_track_rect.y + 10))
        else:
            pygame.draw.rect(screen, (40, 40, 50), self.ior_slider_rect, border_radius=5)
            pygame.draw.rect(screen, LOCKED_COLOR, self.ior_slider_rect, 2, border_radius=5)
            self.draw_lock(screen, self.ior_slider_rect.centerx, self.ior_slider_rect.y + 15, 20)
            txt = self.small.render("Custom Refraction", True, GRAY)
            screen.blit(txt, (self.ior_slider_rect.centerx - 50, self.ior_slider_rect.y + 28))
            cost_txt = self.small.render(f"{self.shop.CUSTOM_REFRACTION_COST}*", True, GOLD)
            screen.blit(cost_txt, (self.ior_slider_rect.centerx - 10, self.ior_slider_rect.y + 45))
    
    def draw(self):
        # Use fixed virtual resolution for all drawing coordinates
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        self.screen.fill(BG_COLOR)
        
        if self.state == "menu":
            self.menu_bg.draw(self.screen)
            
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill((15, 15, 25, 160))
            self.screen.blit(overlay, (0, 0))
            
            t = self.big.render("HODSON LIGHT BOX", True, HIGHLIGHT)
            self.screen.blit(t, (w//2 - 250, 40))
            self.screen.blit(self.small.render("Optics Laboratory", True, GRAY), (w//2 - 60, 90))
            
            pygame.draw.rect(self.screen, PANEL_COLOR, self.settings_btn, border_radius=5)
            pygame.draw.rect(self.screen, GRAY, self.settings_btn, 2, border_radius=5)
            self.screen.blit(self.font.render("Settings", True, WHITE), (self.settings_btn.x + 25, self.settings_btn.y + 8))
            
            pygame.draw.rect(self.screen, PANEL_COLOR, self.shop_btn, border_radius=5)
            pygame.draw.rect(self.screen, GOLD, self.shop_btn, 2, border_radius=5)
            self.screen.blit(self.font.render(f"Shop: {self.shop.stars}*", True, GOLD), (self.shop_btn.x + 20, self.shop_btn.y + 8))
            
            for i, btn in enumerate(self.lvl_btns[:10]):
                level_num = i + 1
                is_unlocked = self.shop.is_level_unlocked(level_num)
                has = self.scoreboard.get_best(level_num) is not None
                
                if not is_unlocked:
                    col = (30, 30, 35)
                    border_col = LOCKED_COLOR
                else:
                    col = PANEL_COLOR if has else (40, 40, 50)
                    border_col = ACCENT_COLOR
                
                pygame.draw.rect(self.screen, col, btn, border_radius=10)
                pygame.draw.rect(self.screen, border_col, btn, 2, border_radius=10)
                
                num_surf = self.big.render(str(level_num), True, WHITE if is_unlocked else GRAY)
                num_rect = num_surf.get_rect(center=(btn.centerx, btn.centery - 10))
                self.screen.blit(num_surf, num_rect)
                
                if not is_unlocked:
                    self.draw_lock(self.screen, btn.right - 20, btn.top + 15, 20)
                else:
                    self.draw_trophy(self.screen, btn.right - 20, btn.top + 20, 18)
                    
                    best = self.scoreboard.get_best(level_num)
                    if best:
                        stars = self.get_stars(best.score)
                        for s in range(3):
                            self.draw_star(self.screen, btn.centerx - 30 + s*20, btn.centery + 25, 6, s < stars)
            
            if self.show_scores:
                ov = pygame.Surface((w, h), pygame.SRCALPHA)
                ov.fill((0, 0, 0, 200))
                self.screen.blit(ov, (0, 0))
                
                pw, ph = 500, 400
                pop = pygame.Rect(w//2 - pw//2, h//2 - ph//2, pw, ph)
                pygame.draw.rect(self.screen, PANEL_COLOR, pop, border_radius=15)
                pygame.draw.rect(self.screen, ACCENT_COLOR, pop, 3, border_radius=15)
                
                self.screen.blit(self.font.render(f"Level {self.viewing_level} High Scores", True, GOLD), (pop.centerx - 120, pop.y + 20))
                
                cb = pygame.Rect(pop.right - 50, pop.y + 10, 40, 40)
                pygame.draw.rect(self.screen, RED, cb, border_radius=5)
                self.screen.blit(self.font.render("X", True, WHITE), (cb.x + 12, cb.y + 5))
                
                lb = pygame.Rect(pop.x + 10, pop.centery - 30, 60, 60)
                rb = pygame.Rect(pop.right - 70, pop.centery - 30, 60, 60)
                pygame.draw.polygon(self.screen, GRAY, [(lb.centerx+15, lb.y+5), (lb.centerx-15, lb.centery), (lb.centerx+15, lb.bottom-5)])
                pygame.draw.polygon(self.screen, GRAY, [(rb.centerx-15, rb.y+5), (rb.centerx+15, rb.centery), (rb.centerx-15, rb.bottom-5)])
                
                top = self.scoreboard.get_top(self.viewing_level)
                if top:
                    y = pop.y + 80
                    for i, e in enumerate(top[:5]):
                        c = GOLD if i == 0 else (SILVER if i == 1 else (BRONZE if i == 2 else WHITE))
                        self.screen.blit(self.font.render(f"{i+1}. {e.name} - {e.score}", True, c), (pop.x + 80, y))
                        y += 50
                else:
                    self.screen.blit(self.font.render("No scores yet!", True, GRAY), (pop.centerx - 80, pop.centery))
                
                self.screen.blit(self.small.render("Click arrows to browse", True, GRAY), (pop.centerx - 80, pop.bottom - 40))
        
        elif self.state == "settings":
            self.screen.blit(self.big.render("SETTINGS", True, HIGHLIGHT), (w//2 - 100, 100))
            
            cb = pygame.Rect(w//2 - 120, h//2 - 50, 240, 50)
            col = RED if self.confirm_clear else PANEL_COLOR
            pygame.draw.rect(self.screen, col, cb, border_radius=8)
            pygame.draw.rect(self.screen, WHITE, cb, 2, border_radius=8)
            txt = "CONFIRM CLEAR?" if self.confirm_clear else "CLEAR ALL DATA"
            self.screen.blit(self.font.render(txt, True, WHITE), (cb.centerx - 70, cb.centery - 12))
            
            bb = pygame.Rect(w//2 - 100, h//2 + 50, 200, 50)
            pygame.draw.rect(self.screen, PANEL_COLOR, bb, border_radius=8)
            pygame.draw.rect(self.screen, GRAY, bb, 2, border_radius=8)
            self.screen.blit(self.font.render("BACK", True, WHITE), (bb.centerx - 35, bb.centery - 12))
        
        elif self.state == "shop":
            self.screen.blit(self.big.render("ITEM SHOP", True, GOLD), (w//2 - 120, 50))
            self.screen.blit(self.font.render(f"Your Stars: {self.shop.stars}", True, GOLD), (w//2 - 100, 100))
            
            y = 160
            for t in ItemType:
                name = t.value.replace('_', ' ').title()
                self.screen.blit(self.font.render(name, True, WHITE), (w//2 - 200, y))
                
                if self.shop.unlocked[t]:
                    self.screen.blit(self.font.render("UNLOCKED", True, GREEN), (w//2 + 50, y))
                else:
                    cost = self.shop.COSTS[t]
                    self.draw_lock(self.screen, w//2 + 70, y - 5, 25)
                    self.screen.blit(self.font.render(f"{cost}*", True, GOLD if self.shop.stars >= cost else GRAY), (w//2 + 100, y))
                    
                    if self.shop.stars >= cost:
                        bb = pygame.Rect(w//2 + 180, y - 5, 80, 35)
                        pygame.draw.rect(self.screen, GREEN, bb, border_radius=5)
                        self.screen.blit(self.small.render("BUY", True, WHITE), (bb.x + 28, bb.y + 8))
                y += 50
            
            y += 20
            self.screen.blit(self.font.render("Custom Refraction", True, WHITE), (w//2 - 200, y))
            if self.shop.custom_refraction_unlocked:
                self.screen.blit(self.font.render("UNLOCKED", True, GREEN), (w//2 + 50, y))
            else:
                self.draw_lock(self.screen, w//2 + 70, y - 5, 25)
                self.screen.blit(self.font.render(f"{self.shop.CUSTOM_REFRACTION_COST}*", True, 
                                GOLD if self.shop.stars >= self.shop.CUSTOM_REFRACTION_COST else GRAY), (w//2 + 100, y))
                
                if self.shop.stars >= self.shop.CUSTOM_REFRACTION_COST:
                    bb = pygame.Rect(w//2 + 180, y - 5, 80, 35)
                    pygame.draw.rect(self.screen, GREEN, bb, border_radius=5)
                    self.screen.blit(self.small.render("BUY", True, WHITE), (bb.x + 28, bb.y + 8))
            
            bb = pygame.Rect(50, h - 100, 140, 40)
            pygame.draw.rect(self.screen, PANEL_COLOR, bb, border_radius=5)
            pygame.draw.rect(self.screen, GRAY, bb, 2, border_radius=5)
            self.screen.blit(self.font.render("Back", True, WHITE), (bb.x + 40, bb.y + 8))
        
        elif self.state in ["playing", "countdown"]:
            for x in range(0, w, 50):
                pygame.draw.line(self.screen, (25, 25, 35), (x, 0), (x, h))
            for y in range(0, h, 50):
                pygame.draw.line(self.screen, (25, 25, 35), (0, y), (w, y))
            
            pygame.draw.rect(self.screen, PANEL_COLOR, (0, 0, 220, h))
            pygame.draw.line(self.screen, ACCENT_COLOR, (220, 0), (220, h), 2)
            
            self.screen.blit(self.font.render(f"Items: {self.level.budget}", True, WHITE), (20, 100))
            
            y = 150
            for t in ItemType:
                rect = pygame.Rect(30, y, 180, 40)
                unlocked = self.shop.unlocked.get(t, False)
                
                if unlocked:
                    can = self.level.budget > 0
                    col = ACCENT_COLOR if can else DARK_GRAY
                    txt = WHITE
                else:
                    col = (60, 60, 70)
                    txt = GRAY
                
                pygame.draw.rect(self.screen, col, rect, border_radius=5)
                
                if not unlocked:
                    self.draw_lock(self.screen, rect.right - 20, rect.centery - 10, 18)
                
                name = t.value.replace('_', ' ').title()
                self.screen.blit(self.small.render(name, True, txt), (rect.x + 10, rect.y + 12))
                y += 48
            
            self.draw_ior_slider()
            
            hints = ["Left: Place/Drag", "Right: Remove", "Yellow: Rotate"]
            for i, ln in enumerate(hints):
                self.screen.blit(self.small.render(ln, True, GRAY), (20, 560 + i * 22))
            
            pygame.draw.rect(self.screen, PANEL_COLOR, self.menu_btn, border_radius=5)
            pygame.draw.rect(self.screen, GRAY, self.menu_btn, 2, border_radius=5)
            self.screen.blit(self.font.render("Menu", True, WHITE), (self.menu_btn.x + 40, self.menu_btn.y + 8))
            
            self.screen.blit(self.font.render(f"Level {self.level_num}", True, WHITE), (20, 20))
            self.screen.blit(self.small.render(f"Score: {self.calc_score()}", True, WHITE), (20, 50))
            
            for s in self.level.sensors:
                s.draw(self.screen)
            for item in self.items:
                item.draw(self.screen)
            self.level.box.draw(self.screen)
            
            for r in self.rays:
                if len(r.path) > 1:
                    fade = self.get_intensity_at_distance(r.distance_traveled)
                    if fade <= 0:
                        continue
                    
                    alpha = int(255 * fade * r.intensity)
                    
                    if r.is_white:
                        s = pygame.Surface((w, h), pygame.SRCALPHA)
                        pygame.draw.lines(s, (255, 255, 255, alpha), False, r.path, 4)
                        self.screen.blit(s, (0, 0))
                        if fade > 0.5:
                            s2 = pygame.Surface((w, h), pygame.SRCALPHA)
                            pygame.draw.lines(s2, (255, 255, 255, int(alpha * 0.3)), False, r.path, 8)
                            self.screen.blit(s2, (0, 0))
                    else:
                        s = pygame.Surface((w, h), pygame.SRCALPHA)
                        pygame.draw.lines(s, (*r.color, alpha), False, r.path, 3)
                        self.screen.blit(s, (0, 0))
            
            if self.state == "countdown":
                ov = pygame.Surface((w, h), pygame.SRCALPHA)
                ov.fill((0, 0, 0, 150))
                self.screen.blit(ov, (0, 0))
                t = self.huge.render(str(self.countdown), True, GREEN)
                self.screen.blit(t, t.get_rect(center=(w//2, h//2)))
        
        elif self.state == "complete":
            ov = pygame.Surface((w, h), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 230))
            self.screen.blit(ov, (0, 0))
            
            self.screen.blit(self.big.render("LEVEL COMPLETE!", True, GREEN), (w//2 - 200, h//2 - 150))
            self.screen.blit(self.font.render(f"Score: {self.final_score}", True, WHITE), (w//2 - 80, h//2 - 80))
            
            stars = self.get_stars(self.final_score)
            for i in range(3):
                self.draw_star(self.screen, w//2 - 60 + i*60, h//2 - 20, 25, i < stars)
            
            self.screen.blit(self.font.render("Enter initials:", True, WHITE), (w//2 - 80, h//2 + 30))
            
            ib = pygame.Rect(w//2 - 60, h//2 + 70, 120, 50)
            pygame.draw.rect(self.screen, WHITE, ib, 2)
            self.screen.blit(self.big.render(self.name if self.name else "___", True, WHITE), (ib.x + 20, ib.y + 5))
            
            sb = pygame.Rect(w//2 - 60, h//2 + 140, 120, 40)
            cs = len(self.name) == 3
            pygame.draw.rect(self.screen, GREEN if cs else GRAY, sb, border_radius=5)
            self.screen.blit(self.font.render("Submit", True, WHITE), (sb.x + 25, sb.y + 8))
        
        elif self.state == "scoreboard":
            self.confetti.draw(self.screen)
            
            ov = pygame.Surface((w, h), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 240))
            self.screen.blit(ov, (0, 0))
            
            self.screen.blit(self.big.render("SCOREBOARD", True, GOLD), (w//2 - 150, 80))
            self.screen.blit(self.font.render(f"Level {self.level_num}", True, WHITE), (w//2 - 50, 140))
            
            stars_this_level = self.get_stars(self.final_score)
            self.screen.blit(self.font.render(f"Stars earned: {stars_this_level}", True, GOLD), (w//2 - 100, 180))
            
            for i in range(3):
                self.draw_star(self.screen, w//2 - 40 + i*40, 230, 20, i < stars_this_level)
            
            top = self.scoreboard.get_top(self.level_num)
            y = 280
            
            current_pos = 0
            for i, e in enumerate(top):
                if e.name == self.name.upper() and e.score == self.final_score:
                    current_pos = i + 1
                    break
            
            for i, e in enumerate(top[:5]):
                is_player = (e.name == self.name.upper() and e.score == self.final_score)
                c = GOLD if is_player else WHITE
                self.screen.blit(self.font.render(f"{i+1}. {e.name} - {e.score}", True, c), (w//2 - 150, y))
                y += 45
            
            if current_pos > 0:
                if 11 <= current_pos % 100 <= 13:
                    suffix = "th"
                else:
                    suffix = {1: "st", 2: "nd", 3: "rd"}.get(current_pos % 10, "th")
                self.screen.blit(self.small.render(f"You came {current_pos}{suffix}!", True, GOLD), (w//2 - 60, y + 10))
            
            if self.bonus_message:
                self.screen.blit(self.small.render(self.bonus_message, True, GREEN), (w//2 - 120, y + 35))
            
            cb = pygame.Rect(w//2 - 80, h - 150, 160, 50)
            pygame.draw.rect(self.screen, GREEN, cb, border_radius=8)
            self.screen.blit(self.font.render("Continue", True, WHITE), (cb.x + 30, cb.y + 12))
        
        pygame.display.flip()
    
    def handle(self):
        mp = Vector2(*pygame.mouse.get_pos())
        # Use fixed virtual resolution for mouse coordinate logic
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            
            # Handle window resize - with SCALED flag, pygame automatically scales
            # We just need to ensure we don't recreate the display surface
            if e.type == pygame.VIDEORESIZE:
                # With SCALED flag, the surface stays 1280x720 and pygame handles the scaling
                # No need to recreate the display or update rect positions
                pass
            
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F11:
                    self.toggle_fullscreen()
            
            if e.type == pygame.MOUSEBUTTONDOWN:
                if self.state == "menu":
                    if self.show_scores:
                        pw, ph = 500, 400
                        pop = pygame.Rect(w//2 - pw//2, h//2 - ph//2, pw, ph)
                        
                        if pygame.Rect(pop.right - 50, pop.y + 10, 40, 40).collidepoint(mp.x, mp.y):
                            self.show_scores = False
                            continue
                        
                        if pygame.Rect(pop.x + 10, pop.centery - 30, 60, 60).collidepoint(mp.x, mp.y):
                            self.viewing_level = max(1, self.viewing_level - 1)
                            continue
                        if pygame.Rect(pop.right - 70, pop.centery - 30, 60, 60).collidepoint(mp.x, mp.y):
                            self.viewing_level = min(10, self.viewing_level + 1)
                            continue
                        
                        if not pop.collidepoint(mp.x, mp.y):
                            self.show_scores = False
                            continue
                    
                    if self.settings_btn.collidepoint(mp.x, mp.y):
                        self.state = "settings"
                        continue
                    if self.shop_btn.collidepoint(mp.x, mp.y):
                        self.state = "shop"
                        continue
                    
                    for i, btn in enumerate(self.lvl_btns[:10]):
                        level_num = i + 1
                        big_btn = btn.inflate(10, 10)
                        if big_btn.collidepoint(mp.x, mp.y):
                            if not self.shop.is_level_unlocked(level_num):
                                continue
                            
                            tr = pygame.Rect(btn.right - 40, btn.y, 40, 40)
                            if tr.collidepoint(mp.x, mp.y):
                                self.show_scores = True
                                self.viewing_level = level_num
                            else:
                                self.start_level(level_num)
                            break
                
                elif self.state == "settings":
                    if pygame.Rect(w//2 - 120, h//2 - 50, 240, 50).collidepoint(mp.x, mp.y):
                        if not self.confirm_clear:
                            self.confirm_clear = True
                        else:
                            self.scoreboard.clear()
                            self.shop.clear_all()
                            if os.path.exists('scores.json'):
                                os.remove('scores.json')
                            if os.path.exists('shop.json'):
                                os.remove('shop.json')
                            self.confirm_clear = False
                    elif pygame.Rect(w//2 - 100, h//2 + 50, 200, 50).collidepoint(mp.x, mp.y):
                        self.state = "menu"
                        self.confirm_clear = False
                
                elif self.state == "shop":
                    y = 160
                    for t in ItemType:
                        if not self.shop.unlocked[t]:
                            if pygame.Rect(w//2 + 180, y - 5, 80, 35).collidepoint(mp.x, mp.y):
                                self.shop.unlock(t)
                        y += 50
                    
                    y += 20
                    if not self.shop.custom_refraction_unlocked:
                        if pygame.Rect(w//2 + 180, y - 5, 80, 35).collidepoint(mp.x, mp.y):
                            self.shop.unlock_custom_refraction()
                    
                    if pygame.Rect(50, h - 100, 140, 40).collidepoint(mp.x, mp.y):
                        self.state = "menu"
                
                elif self.state in ["playing", "countdown"]:
                    if e.button == 1:
                        if self.shop.custom_refraction_unlocked and self.ior_slider_rect.collidepoint(mp.x, mp.y):
                            self.ior_dragging = True
                            rel_x = max(0, min(mp.x - self.ior_track_rect.x, self.ior_track_rect.width))
                            ratio = rel_x / self.ior_track_rect.width
                            new_ior = 1.1 + ratio * 0.9
                            self.shop.update_ior(new_ior)
                            continue
                        
                        y = 150
                        for t in ItemType:
                            big = pygame.Rect(30, y - 2, 190, 44)
                            if big.collidepoint(mp.x, mp.y):
                                self.spawn(t)
                                break
                            y += 48
                        
                        if self.menu_btn.inflate(10, 10).collidepoint(mp.x, mp.y):
                            self.state = "menu"
                        
                        if self.level.box.corner_contains(mp):
                            self.level.box.rotating = True
                            dx = mp.x - self.level.box.pos.x
                            dy = mp.y - self.level.box.pos.y
                            angle_to_mouse = math.degrees(math.atan2(dy, dx))
                            self.level.box.angle_offset = self.level.box.angle - angle_to_mouse
                        
                        elif self.level.box.contains(mp):
                            self.level.box.dragging = True
                            self.level.box.offset = Vector2(mp.x - self.level.box.pos.x, mp.y - self.level.box.pos.y)
                        
                        for item in self.items:
                            if (item.get_handle() - mp).length() < 15:
                                item.rotating = True
                                dx = mp.x - item.pos.x
                                dy = mp.y - item.pos.y
                                angle_to_mouse = math.degrees(math.atan2(dy, dx))
                                item.rotation_offset = item.rotation - angle_to_mouse
                                break
                            elif item.contains(mp):
                                item.dragging = True
                                item.drag_offset = Vector2(mp.x - item.pos.x, mp.y - item.pos.y)
                                self.dragged = item
                                break
                    
                    elif e.button == 3:
                        for item in self.items:
                            if item.contains(mp):
                                self.remove(item)
                                break
                
                elif self.state == "complete":
                    if e.button == 1 and pygame.Rect(w//2 - 60, h//2 + 140, 120, 40).collidepoint(mp.x, mp.y) and len(self.name) == 3:
                        ent = ScoreEntry(self.name.upper(), self.final_score, self.level_num)
                        self.position = self.scoreboard.add(ent)
                        self.last_name = self.name.upper()
                        self.stars_earned, _, self.bonus_message = self.shop.award(self.level_num, self.get_stars(self.final_score))
                        self.confetti.burst(w//2, h//2)
                        self.state = "scoreboard"
                
                elif self.state == "scoreboard":
                    if e.button == 1 and pygame.Rect(w//2 - 80, h - 150, 160, 50).inflate(20, 20).collidepoint(mp.x, mp.y):
                        if self.level_num < 10:
                            self.start_level(self.level_num + 1)
                        else:
                            self.state = "menu"
                            self.confetti = Confetti()
            
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                self.ior_dragging = False
                if self.level:
                    self.level.box.dragging = False
                    self.level.box.rotating = False
                    for item in self.items:
                        item.dragging = False
                        item.rotating = False
                        item.constrain(w, h)
                    if self.level.box.dragging:
                        self.level.box.constrain(w, h)
                    self.dragged = None
            
            elif e.type == pygame.MOUSEMOTION:
                if self.ior_dragging and self.shop.custom_refraction_unlocked:
                    rel_x = max(0, min(mp.x - self.ior_track_rect.x, self.ior_track_rect.width))
                    ratio = rel_x / self.ior_track_rect.width
                    new_ior = 1.1 + ratio * 0.9
                    self.shop.update_ior(new_ior)
                
                if self.state in ["playing", "countdown"] and self.level:
                    if self.level.box.dragging:
                        self.level.box.pos = mp - self.level.box.offset
                    elif self.level.box.rotating:
                        dx = mp.x - self.level.box.pos.x
                        dy = mp.y - self.level.box.pos.y
                        angle_to_mouse = math.degrees(math.atan2(dy, dx))
                        self.level.box.angle = angle_to_mouse + self.level.box.angle_offset
                    
                    for item in self.items:
                        if item.dragging:
                            item.pos = mp - item.drag_offset
                            item.update_shape()
                        elif item.rotating:
                            dx = mp.x - item.pos.x
                            dy = mp.y - item.pos.y
                            angle_to_mouse = math.degrees(math.atan2(dy, dx))
                            item.rotation = angle_to_mouse + item.rotation_offset
                            item.update_shape()
            
            elif e.type == pygame.KEYDOWN and self.state == "complete":
                if e.key == pygame.K_BACKSPACE:
                    self.name = self.name[:-1]
                elif e.key == pygame.K_RETURN and len(self.name) == 3:
                    ent = ScoreEntry(self.name.upper(), self.final_score, self.level_num)
                    self.position = self.scoreboard.add(ent)
                    self.last_name = self.name.upper()
                    self.stars_earned, _, self.bonus_message = self.shop.award(self.level_num, self.get_stars(self.final_score))
                    self.confetti.burst(w//2, h//2)
                    self.state = "scoreboard"
                elif len(self.name) < 3 and e.unicode.isalpha():
                    self.name += e.unicode.upper()
        
        return True
    
    def run(self):
        while self.handle():
            self.update()
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()

if __name__ == "__main__":
    Game().run()