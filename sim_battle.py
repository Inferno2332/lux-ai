#!/usr/bin/env python
# coding: utf-8


import numpy as np
from kaggle_environments import make

def sim_battle(agent0, agent1, sample_size= 100):
    # Simulates battles between two agents
    #  returns W/ D /L as a dict and win rate

    wins, draw, loss= 0, 0 ,0

    rng= np.random.randint(1, 10**7, size=sample_size)

    for seed in rng:

        env = make("lux_ai_2021", configuration={"seed": int(seed), "loglevel": 0, "annotations": True}, debug=True)
        steps = env.run([agent0, agent1])

        # if agent 0 final score > agent 1 add win 
        a0_score= [env.state[0]['reward'] if env.state[0]['reward'] != None else 0]
        a1_score= [env.state[1]['reward'] if env.state[1]['reward'] != None else 0]

        if a0_score > a1_score:
            wins+= 1
        elif a0_score == a1_score:
            draw+=1
        else:
            loss+=1
        
        win_rate= (wins+ draw*0.5)/sample_size

    return {"Wins": wins, "Draws" :draw, "Losses": loss, "Win rate": win_rate}
