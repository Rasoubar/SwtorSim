This is a preliminary readme

/src/swtorsim files:

engine -> makes and progresses heapqueue.
combat_math -> does the math for any hits
events -> anything that will be schedues in the heapqueue from the simulation goes here
rotation -> handles rotations, which determine our cast attempts .Is very basic rn. The PriorityRotation is shit, wil make a proper one soon.
requirements -> used to validate both abilities and actions. the way it's setup I found cute, i guess not idea for performance but good for being able to check what's wrong rn.
config_load -> loads the json files. I didn't write this code, I mostly wanted to load them to test out. Will learn and improve it soon.
entities -> everything that is in the run for more than it's own execution goes here. 
abilities -> might rename to actions. or make an action file. Anything player actively does is an ability and the actions an ability causes are actions. All it's logic is here.
batch -> handles batch processing
metrics -> logs damage and source


process:
 - schedule time limit
 - schedule passive force gain's 1st instance
 - we schedule the player to act at the start
 - player.rotation is resolved.
 - tries to cast ability that is in current step of rotation
 	- if fails, doesn't move rotation along, reschedules the player to act again. (rn is 0.1s because it was process of testing, this logic will be changed)
 - if success:
	-ability has been casted
	-moves rotation along to the next step.
	-next gcd has been calculated using the data fro the ability
	-schedules the player to act on the next gcd
This keeps going until the time limit is over. Will ofc change what ends it.

ability resolution:
  - we try to cast the ability
  - we check if we can:
  	- we check if we respect the gcd and if so, if it's time for it (this doesn't really make sense right now, it's redundant, the cast scheduling happens taking into gcd into account)
  	- check if cooldown for ability is 0
  	- check if we can afford the ability
  	- check if we meet all ability specific restrictions
  - we cast the ability if we can
	- we spend the force
	- we apply cooldown and gcd
	- we execute all the actions of the ability

action resolution: 
  - we check if the action's restrictions are respected
  - we check if the action has a random's chance and if it is met
  - we check if the action has aplication delay (1st hits and vent heat do)
  - we discern the type of action
	- if it's damage, we schedule the damage to happen acording to delay
	- dot we get the dot data and apply it. right my dot implementation differs from the game for the 1st hit. Will be fixed.
	- buffs/debuffs same thing as dot, but dot as it's own class. we also schedule when they end.
		- buffs if the chosen buff alters player stats we recalculate them. same as when it expires.
	- resource_gain we schedule the resource gain acording to delay
	- cooldown_mod we alter the cooldown of the abilities that fit the action's tags acording to action's instructions

damage hit calculation:
  - we alter the modifiers acording to their tags and the player's tags. some with diferent IDs are adictive so we have buckets for them. yay.
  - we load the relevant action data
  - we do the calculation depending on attack_type in the ability.
  - we see if we need to apply armor dr.
  - we apply to modifiers.
  - see if it's crit and if so apply modifier
  - return the number and wether or not it was crit
  
  