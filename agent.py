# for kaggle-environments
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
import math
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

def random_free(unit, targets):
    dirs = ['n', 's', 'e', 'w']
    random.shuffle(dirs)
    
    for direc in dirs:
        new_target = unit.pos.translate(direc, 1)
        if (new_target not in targets) and (new_target.x < game_state.map_width) and (new_target.y < game_state.map_height):
            banned.append(new_target)
            return new_target, direc
        
    return unit.pos, 'c'

def collision_avoider(targets, target, actions, action, unit, city_tiles):
    #Detects if proposed move will lead to collision. If so, dont move.
    
    #Input: targets, (proposed) target, action, (proposed) action, units.
    
    #Output: action
    
    if target in targets and target not in city_tiles:
        #Sit still if staying is not target
        if unit.pos not in targets:
            action= unit.move('c')   
            actions.append(action)
            
            if unit.pos not in city_tiles:
                targets.append(unit.pos)
        
        #Else move in a random direction to not collide
        else:
            target, direc= random_free(unit, targets)
            action= unit.move(direc)
            
            actions.append(action)
            targets.append(target)      
            
    else:
        actions.append(action)
        targets.append(target)
    
    return targets, actions

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
    
    #Default= build new cities unless not enough fuel...
    new_city = True
    
    #Keep track of turn no. and day night cycle.
    turn= game_state.turn
    
    if turn%40 >30:
        night= True
        turns_to_night=0
    else:
        night=False
        turns_to_night = 30- turn%40
    
    #Copy resource tiles 
    resource_tiles_copy=resource_tiles.copy()
    
    #Keep a list of target locations
    prev_loc=[unit.pos for unit in player.units]
    
    #Include not acting workers 
    targets=[]
    
    for unit in player.units:
        if unit.can_act()== False:
            targets.append(unit.pos)
    
    #Keep track of player/ opponent city tiles
    city_tiles=[]
    
    for city in player.cities:
        
        for tile in player.cities[city].citytiles:
            city_tiles.append(tile.pos)
    
    opp_city_tiles=[]

    for city in opponent.cities:
        for tile in opponent.cities[city].citytiles:
            opp_city_tiles.append(tile.pos)
    
    research_points=player.research_points
    
    #add targets to banned list
    targets= targets + opp_city_tiles
        
    for city in player.cities.values():
        #Required fuel to build new city should be a function of no. turns to night and expected fuel gain during the day
        
        req_fuel = (10- turns_to_night*0.33)//1 * city.get_light_upkeep() 
        
        if city.fuel < req_fuel:
            # let's not build a new one yet
            new_city = False
            
        # Do stuff with our citytiles
        for tile in city.citytiles:
            if tile.can_act():
                
                # If we have fewer units than cities create a unit
                if len(player.units) < sum([len(city.citytiles) for city in player.cities.values()]):
                    action = tile.build_worker()
                    actions.append(action)
                
                # Otherwise do research
                elif research_points <200:
                    action = tile.research()
                    actions.append(action)
                    research_points+=1
                
                #Else build worker or cart?
                
                else:
                    action = tile.build_worker()
                    actions.append(action)
                    
    
    for unit in player.units:
        # if the unit is a worker (can mine resources) and can perform an action this turn
        if unit.is_worker() and unit.can_act():
            
            # Find the closest city tile and its distance from the unit
            closest_city_tile = find_closest_city_tile(unit.pos, player)
            d = unit.pos.distance_to(closest_city_tile.pos)
            
            late_game=330
            
            if ( 5 > turns_to_night and (turn <late_game or turn >350) )  or night==True: 
                
                #  If nearing night time, head to city
                action = unit.move(unit.pos.direction_to(closest_city_tile.pos)) 
                
                direction= unit.pos.direction_to(closest_city_tile.pos)
                
                target= unit.pos.translate(direction,1)
                
                targets, actions= collision_avoider(targets, target, actions, action, unit, city_tiles)
                
                continue
                
            #Special late game rules
                
            if late_game < turn < 350 and unit.can_build(game_state.map) and d==1:
                    
                    action = unit.build_city()
                    actions.append(action)                              
                    targets.append(unit.pos)
                    
                    city_tiles.append(unit.pos)
                                              
                
            elif 5 > turns_to_night:
                    action = unit.move(unit.pos.direction_to(closest_city_tile.pos)) 
                
                    direction= unit.pos.direction_to(closest_city_tile.pos)
                    
                    target= unit.pos.translate(direction,1)
                
                    targets, actions= collision_avoider(targets, target, actions, action, unit, city_tiles)
                
                    continue
            
            elif unit.can_build(game_state.map) and ((new_city and d > 0) or closest_city_tile is None):
                    action = unit.build_city()
                    actions.append(action)
                    
                    targets.append(unit.pos)
            
            # we want to mine only if there is space left in the worker's cargo
            elif unit.get_cargo_space_left() > 0:
                # find the closest resource if it exists to this unit
                
                closest_resource_tile = find_closest_resources(unit.pos, player, resource_tiles_copy)
                
                if closest_resource_tile is not None:
                    
                    i= resource_tiles_copy.index(closest_resource_tile)
                    
                    # create a move action to move this unit in the direction of the closest resource tile and add to our actions list
                    action = unit.move(unit.pos.direction_to(closest_resource_tile.pos))
                    
                    #insert code to check if action will lead to collision... if so then say in center 
                    direction= unit.pos.direction_to(closest_city_tile.pos)
                
                    target= unit.pos.translate(direction,1)
                
                    targets, actions= collision_avoider(targets, target, actions, action, unit, city_tiles)
                    
                    del resource_tiles_copy[i]
                    #Dont let agents have the same closest resource (dont compete and collide, hopefully)
                
                else:
                    #no resource? go home
                    action = unit.move(unit.pos.direction_to(closest_city_tile.pos)) 
                
                    direction= unit.pos.direction_to(closest_city_tile.pos)
                
                    target= unit.pos.translate(direction,1)
                
                    targets, actions= collision_avoider(targets, target, actions, action, unit, city_tiles)

            else:
                # find the closest citytile and move the unit towards it to drop resources to a citytile to fuel the city
                if closest_city_tile is not None:
                    # create a move action to move this unit in the direction of the closest resource tile and add to our actions list
                    action = unit.move(unit.pos.direction_to(closest_city_tile.pos))
                    
                    direction= unit.pos.direction_to(closest_city_tile.pos)
                
                    target= unit.pos.translate(direction,1)
                
                    targets, actions= collision_avoider(targets, target, actions, action, unit, city_tiles)
                    
    return actions
