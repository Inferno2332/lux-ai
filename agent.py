import sys
import math
from lux.game import Game
from lux.game_objects import Unit, Player, City, CityTile
from lux.game_map import Cell, Position, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
from enum import Enum
import random
from typing import Optional
from itertools import chain

DIRECTIONS = Constants.DIRECTIONS
game_state = None


def log(msg):
    print(f"Turn {game_state.turn}: {msg}", file=sys.stderr)


class UnitGoal(Enum):
    IDLE = 0  # Unassigned
    BUILD = 1  # Build at target
    GATHER = 2  # Gather resources for target
    RETURN = 3  # Return to target with resources


class UnitState():

    def __init__(self, unit_id):
        self.unit_id = unit_id
        self._goal = UnitGoal.IDLE
        self._target = None

    @property
    def goal(self):
        return self._goal

    @goal.setter
    def goal(self, new_goal):
        self._goal = new_goal
        log(f"Goal of {self.unit_id} is set to {self._goal}")

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, new_target):
        self._target = new_target
        log(f"Target of {self.unit_id} is set to {self._target}")


unit_states: dict[str, UnitState] = dict()  # Keep track of unit state


class Cluster():
    """Resource cluster"""

    def __init__(self, tiles):
        self.tiles = tiles
        x_mid = sum(t.x for t in self.tiles) / len(self.tiles)
        y_mid = sum(t.y for t in self.tiles) / len(self.tiles)
        self.centroid = Position(round(x_mid), round(y_mid))


def pos_is_valid(pos: Position):
    return 0 <= pos.x < game_state.map_width and 0 <= pos.y < game_state.map_height


def neighbours(pos: Position):
    for direction in [DIRECTIONS.NORTH, DIRECTIONS.WEST, DIRECTIONS.SOUTH, DIRECTIONS.EAST]:
        new_pos = pos.translate(direction, 1)
        if pos_is_valid(new_pos):
            yield new_pos


def boundary(region: list[Position]):
    region_set = set((pos.x, pos.y) for pos in region)
    bd = set()
    for pos in region:
        for nb in neighbours(pos):
            if (nb.x, nb.y) not in region_set and (nb.x, nb.y) not in bd:
                bd.add((nb.x, nb.y))
                yield nb


def cell_is_empty(cell: Cell) -> bool:
    return not cell.has_resource() and cell.citytile is None


def cycle_num() -> int:
    return game_state.turn // 40


def cycle_turn() -> int:
    return game_state.turn % 40


def is_day():
    return cycle_turn() < 30


def is_night():
    return cycle_turn() >= 30


def turns_to_night():
    return max(30 - cycle_turn(), 0)


def survives_until(city: City) -> int:
    nights_surv = math.floor(city.fuel / city.get_light_upkeep()) + max(cycle_turn() - 30, 0)
    return 40 * (cycle_num() + nights_surv // 10) + 30 + nights_surv % 10


class TurnState():

    def __init__(self, observation):
        self.player: Player = game_state.players[observation.player]
        self.opponent: Player = game_state.players[(observation.player + 1) % 2]
        self.width, self.height = game_state.map.width, game_state.map.height

        self.actions = []  # Actions to perform
        self.occupied = set()  # Cells occupied the next turn

        self._analyse_resources()
        self._analyse_resource_clusters()

        self.cities: list[City] = list(self.player.cities.values())
        self.citytiles: list[CityTile] = [c for city in self.cities for c in city.citytiles]

        self.worker_vacancy = len(self.citytiles) - len(self.player.units)

    def _analyse_resources(self):
        self.wood_tiles = []
        self.coal_tiles = []
        self.uranium_tiles = []
        for y in range(self.height):
            for x in range(self.width):
                cell = game_state.map.get_cell(x, y)
                if cell.has_resource():
                    if cell.resource.type == Constants.RESOURCE_TYPES.WOOD:
                        self.wood_tiles.append(cell.pos)
                    elif cell.resource.type == Constants.RESOURCE_TYPES.COAL:
                        self.coal_tiles.append(cell.pos)
                    elif cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
                        self.uranium_tiles.append(cell.pos)

    def _analyse_resource_clusters(self):
        self.resource_cluster = []
        visited = set()
        for y in range(self.height):
            for x in range(self.width):
                cell = game_state.map.get_cell(x, y)
                if self.cell_is_useful(cell) and (cell.pos.x, cell.pos.y) not in visited:
                    visited.add((cell.pos.x, cell.pos.y))
                    st = [cell.pos]
                    ptr = 0
                    while ptr < len(st):
                        for nb in neighbours(st[ptr]):
                            nb_cell = game_state.map.get_cell_by_pos(nb)
                            if not (self.cell_is_useful(nb_cell) and (nb.x, nb.y) not in visited):
                                continue
                            visited.add((nb.x, nb.y))
                            st.append(nb)
                        ptr += 1

                    self.resource_cluster.append(Cluster(st))

    def move_avoid_collision(self, unit, direction):
        arr = [DIRECTIONS.NORTH, DIRECTIONS.WEST, DIRECTIONS.SOUTH, DIRECTIONS.EAST, DIRECTIONS.CENTER]
        random.shuffle(arr)

        candidates = [direction] + arr
        for candidate in candidates:
            new_pos = unit.pos.translate(candidate, 1)
            if not pos_is_valid(new_pos):
                continue
            if (new_pos.x, new_pos.y) in self.occupied:
                continue
            cell = game_state.map.get_cell_by_pos(new_pos)
            if cell.citytile is not None:
                if cell.citytile.team == self.player.team:
                    return unit.move(candidate)
                else:
                    continue
            self.occupied.add((new_pos.x, new_pos.y))
            return unit.move(candidate)
        log(f"Collision unavoidable for {unit.id}")
        return unit.move(DIRECTIONS.CENTER)

    def tile_score(self, pos: Position):
        """Suitability of building at position"""
        cell = game_state.map.get_cell_by_pos(pos)
        if not cell_is_empty(cell):
            return 0

        nearest_cluster = []
        cluster_dist = math.inf
        for cluster in self.resource_cluster:
            dist = pos.distance_to(cluster.centroid)
            if dist < cluster_dist:
                cluster_dist = dist
                nearest_cluster = cluster.tiles

        est_max = 0.0
        citytile_num = 0
        for tile in nearest_cluster:
            cell = game_state.map.get_cell_by_pos(tile)
            if cell.has_resource():
                if cell.resource.type == Constants.RESOURCE_TYPES.WOOD:
                    est_max += 0.5
                elif cell.resource.type == Constants.RESOURCE_TYPES.COAL:
                    if self.player.researched_coal():
                        est_max += 2.0
                elif cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
                    if self.player.researched_uranium():
                        est_max += 4.0
            if self.cell_has_player_city(cell):
                est_max -= 1.0

        multiplier = 1.0
        for tile in neighbours(pos):
            cell = game_state.map.get_cell_by_pos(tile)
            if cell.has_resource():
                if cell.resource.type == Constants.RESOURCE_TYPES.WOOD:
                    multiplier *= 1.1
                elif cell.resource.type == Constants.RESOURCE_TYPES.COAL:
                    if self.player.researched_coal():
                        multiplier *= 1.5
                elif cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
                    if self.player.researched_uranium():
                        multiplier *= 2.0
        return est_max * multiplier

    def cell_has_player_city(self, cell: Cell):
        return cell.citytile is not None and cell.citytile.team == self.player.team

    def cell_is_useful(self, cell: Cell):
        return cell.has_resource() or self.cell_has_player_city(cell)

    def neighbour_has_usable_resources(self, pos: Position) -> bool:
        for nb in neighbours(pos):
            cell = game_state.map.get_cell_by_pos(nb)
            if not cell.has_resource():
                continue
            if cell.resource.type == Constants.RESOURCE_TYPES.WOOD:
                return True
            elif cell.resource.type == Constants.RESOURCE_TYPES.COAL:
                if self.player.researched_coal():
                    return True
            elif cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
                if self.player.researched_uranium():
                    return True
        return False

    def city_adjacent_resources(self, city: City):
        wood = 0
        coal = 0
        uranium = 0
        for pos in boundary(map(lambda x: x.pos, city.citytiles)):
            cell = game_state.map.get_cell_by_pos(pos)
            if cell.has_resource():
                if cell.resource.type == Constants.RESOURCE_TYPES.WOOD:
                    wood += 1
                elif cell.resource.type == Constants.RESOURCE_TYPES.COAL:
                    coal += 1
                elif cell.resource.type == Constants.RESOURCE_TYPES.URANIUM:
                    uranium += 1
        return (wood, coal, uranium)

    def worker_reassign(self, worker: Unit, worker_state: UnitState):
        """Reassign worker if necessary."""
        if worker_state.goal == UnitGoal.BUILD:
            # Set to IDLE if it is no longer possible to build at target
            target_cell = game_state.map.get_cell_by_pos(worker_state.target)
            if not cell_is_empty(target_cell):
                worker_state.goal = UnitGoal.IDLE
            elif worker.pos == target_cell.pos and worker.get_cargo_space_left() > 0 and not self.neighbour_has_usable_resources(worker.pos):
                worker_state.goal = UnitGoal.IDLE
        elif worker_state.goal == UnitGoal.GATHER:
            if isinstance(worker_state.target, Position):
                worker_state.target = self.player.cities[game_state.map.get_cell_by_pos(worker_state.target).citytile.cityid]
            if worker_state.target not in self.player.cities:
                worker_state.goal = UnitGoal.IDLE
            elif worker.get_cargo_space_left() <= 5 or turns_to_night() <= 2:
                worker_state.goal = UnitGoal.RETURN
        elif worker_state.goal == UnitGoal.RETURN:
            if worker_state.target not in self.player.cities:
                worker_state.goal = UnitGoal.IDLE
            elif turns_to_night() >= 2:
                worker_cell = game_state.map.get_cell_by_pos(worker.pos)
                if worker_cell.citytile is not None and survives_until(self.player.cities[worker_state.target]) >= min(360, game_state.turn + 60):
                    worker_state.goal = UnitGoal.IDLE
                elif worker.get_cargo_space_left() == 100:
                    worker_state.goal = UnitGoal.GATHER

    def worker_assign_idle(self, worker: Unit, worker_state: UnitState):
        city_best = None
        dist_best = math.inf
        for city in self.cities:
            if survives_until(city) >= min(360, game_state.turn + 60):
                continue
            dist = min(citytile.pos.distance_to(worker.pos) for citytile in city.citytiles)
            if dist < dist_best:
                dist_best = dist
                city_best = city

        if city_best is not None:
            worker_state.goal = UnitGoal.GATHER if is_day() else UnitGoal.RETURN
            worker_state.target = city.cityid
            return

        if turns_to_night() >= 5:
            pos_best = None
            pos_score = 0
            for cluster in self.resource_cluster:
                for pos in boundary(cluster.tiles):
                    score = 0
                    if 2 * pos.distance_to(worker.pos) <= turns_to_night():
                        score = self.tile_score(pos) / (1 + max(0, pos.distance_to(worker.pos) - 2 * cycle_num()))
                    if score > pos_score:
                        pos_score = score
                        pos_best = pos

            if pos_best is not None:
                worker_state.goal = UnitGoal.BUILD
                worker_state.target = pos_best

    def worker_perform_goal(self, worker: Unit, worker_state: UnitState) -> Optional[str]:
        if worker_state.goal == UnitGoal.BUILD:
            if worker.pos == worker_state.target:
                if worker.can_build(game_state.map):
                    worker_state.goal = UnitGoal.GATHER
                    return worker.build_city()
            else:
                return self.move_avoid_collision(worker, worker.pos.direction_to(worker_state.target))
        elif worker_state.goal == UnitGoal.GATHER:
            resource_best = None
            score_best = 0.0
            for tile in self.wood_tiles:
                score = 1.0 / (tile.distance_to(worker.pos) + 1)
                if score > score_best:
                    score_best = score
                    resource_best = tile

            if self.player.researched_coal():
                for tile in self.coal_tiles:
                    score = 1.0 / (tile.distance_to(worker.pos) + 1)
                    if score > score_best:
                        score_best = score
                        resource_best = tile

            if self.player.researched_uranium():
                for tile in self.coal_tiles:
                    score = 1.0 / (tile.distance_to(worker.pos) + 1)
                    if score > score_best:
                        score_best = score
                        resource_best = tile

            if resource_best is not None:
                return self.move_avoid_collision(worker, worker.pos.direction_to(resource_best))

        elif worker_state.goal == UnitGoal.RETURN:
            city = self.player.cities[worker_state.target]
            citytile = min(city.citytiles, key=lambda c: c.pos.distance_to(worker.pos))
            return self.move_avoid_collision(worker, worker.pos.direction_to(citytile.pos))

    def get_worker_action(self, worker: Unit, worker_state: UnitState) -> Optional[str]:
        """Return a worker action, given that it can act."""

        self.worker_reassign(worker, worker_state)

        if worker_state.goal == UnitGoal.IDLE:
            self.worker_assign_idle(worker, worker_state)

        return self.worker_perform_goal(worker, worker_state)

    def get_cart_action(self, cart: Unit, cart_state: UnitState) -> Optional[str]:
        # Unimplemented
        return None

    def get_unit_action(self, unit: Unit) -> Optional[str]:
        if unit.id not in unit_states:
            unit_states[unit.id] = UnitState(unit.id)
            log(f"New unit: {unit.id}")
        if unit.can_act():
            if unit.is_worker():
                return self.get_worker_action(unit, unit_states[unit.id])
            elif unit.is_cart():
                return self.get_cart_action(unit, unit_states[unit.id])

    def run_units(self):
        available = []
        for unit in self.player.units:
            if unit.can_act():
                available.append(unit)
            else:
                cell = game_state.map.get_cell_by_pos(unit.pos)
                if cell.citytile is None:
                    self.occupied.add((unit.pos.x, unit.pos.y))
        for unit in available:
            action = self.get_unit_action(unit)
            if action is not None:
                self.actions.append(action)

    def get_citytile_action(self, citytile: CityTile, city: City) -> Optional[str]:
        if self.worker_vacancy > 0:
            if self.player.research_points < 50:
                x = random.random()
                if x < max(0.0, (len(self.citytiles) - 2) * 0.1):
                    return citytile.research()
                else:
                    self.worker_vacancy -= 1
                    return citytile.build_worker()
            else:
                self.worker_vacancy -= 1
                return citytile.build_worker()
        elif self.player.research_points < 50:
            citytile.research()

    def run_city(self, city: City):
        for citytile in city.citytiles:
            if not citytile.can_act():
                continue
            action = self.get_citytile_action(citytile, city)
            if action is not None:
                self.actions.append(action)

    def run_cities(self):
        for city in self.cities:
            # log(f"City {city.cityid} survives until {survives_until(city)}")
            self.run_city(city)

    def run(self):
        self.run_units()
        self.run_cities()
        return self.actions


def agent(observation, configuration):
    global game_state

    # Do not edit
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])

    return TurnState(observation).run()
