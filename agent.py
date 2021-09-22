# for kaggle-environments
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
import math
import random
import sys

### Define helper functions

# this snippet finds all resources stored on the map and puts them into a list so we can search over them
def find_resources(game_state):
    resource_tiles: list[Cell] = []
    width, height = game_state.map_width, game_state.map_height
    for y in range(height):
        for x in range(width):
            cell = game_state.map.get_cell(x, y)
            if cell.has_resource():
                resource_tiles.append(cell)
    return resource_tiles

# the next snippet finds the closest resources that we can mine given position on a map
def find_closest_resources(pos, player, resource_tiles):
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in resource_tiles:
        # we skip over resources that we can't mine due to not having researched them
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal(): continue
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium(): continue
        dist = resource_tile.pos.distance_to(pos)
        if dist < closest_dist:
            closest_dist = dist
            closest_resource_tile = resource_tile
    return closest_resource_tile

def find_closest_city_tile(pos, player):
    closest_city_tile = None
    if len(player.cities) > 0:
        closest_dist = math.inf
        # the cities are stored as a dictionary mapping city id to the city object, which has a citytiles field that
        # contains the information of all citytiles in that city
        for k, city in player.cities.items():
            for city_tile in city.citytiles:
                dist = city_tile.pos.distance_to(pos)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_city_tile = city_tile
    return closest_city_tile

def random_dir_except(direc):
    li = ['n', 's', 'e', 'w', 'c']
    li.remove(direc)
    return random.choice(li)

game_state = None
def agent(observation, configuration):
    global game_state

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])
    
    actions = []

    ### AI Code goes down here! ### 
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height

    resource_tiles = find_resources(game_state)
    
    # Fuel only gets used up at night so we need enough to last the nights
    new_city = True
    
    for city in player.cities.values():
        req_fuel = 20 * city.get_light_upkeep() # There are 90 nights total

        if city.fuel < req_fuel:
            # let's not build a new one yet
            new_city = False
            
        # Do stuff with our citytiles
        for tile in city.citytiles:
            pending = 0
            if tile.can_act():
                
                # If we have fewer units than cities create a unit
                if len(player.units) + pending < sum([len(city.citytiles) for city in player.cities.values()]):
                    action = tile.build_worker()
                    actions.append(action)
                    pending += 1
                
                # Otherwise do research
                else:
                    action = tile.research()
                    actions.append(action)

###########################################################                    

    # Where units plan to go
    targets = set()
    
    for unit in player.units:
        # if the unit is a worker (can mine resources) and can perform an action this turn
        if unit.is_worker() and unit.can_act():
            
            # Find the closest city tile and its distance from the unit
            closest_city_tile = find_closest_city_tile(unit.pos, player)
            d = unit.pos.distance_to(closest_city_tile.pos)
            
            if observation["step"] % 40 >= 26: #  FIX THIS LATER. Make it go home properly.
                direction = unit.pos.direction_to(closest_city_tile.pos)
                target = unit.pos.translate(direction, 1)
                    
                if (target.x, target.y) in targets:

                    action = unit.move('c')
                    actions.append(action)

                else:
                    targets.add((target.x, target.y))
                    action = unit.move(direction)
                    actions.append(action)

                continue
                
            
            if (unit.can_build(game_state.map) and new_city and d==1) or closest_city_tile is None:
                action = unit.build_city()
                actions.append(action)
                
            
            # we want to mine only if there is space left in the worker's cargo
            elif unit.get_cargo_space_left() > 0:
                # find the closest resource if it exists to this unit
                closest_resource_tile = find_closest_resources(unit.pos, player, resource_tiles)
                if closest_resource_tile is not None:
                    # create a move action to move this unit in the direction of the closest resource tile and add to our actions list
                    direction = unit.pos.direction_to(closest_resource_tile.pos)
                    target = unit.pos.translate(direction, 1)
                    
                    if (target.x, target.y) in targets:
                        
                        action = unit.move('c')
                        actions.append(action)
                        
                    else:
                        targets.add((target.x, target.y))
                        action = unit.move(direction)
                        actions.append(action)
            else:
                # find the closest citytile and move the unit towards it to drop resources to a citytile to fuel the city
                if closest_city_tile is not None:
                    # create a move action to move this unit in the direction of the closest resource tile and add to our actions list
                    direction = unit.pos.direction_to(closest_city_tile.pos)
                    target = unit.pos.translate(direction, 1)
                    
                    if (target.x, target.y) in targets:
                        action = unit.move('c')
                        actions.append(action)
                        
                    else:
                        targets.add((target.x, target.y))
                        action = unit.move(direction)
                        actions.append(action)
                    
    
    
    return actions
