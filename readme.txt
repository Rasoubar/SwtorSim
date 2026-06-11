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



process:
 - schedule passive force gain's 1st instance
 - we schedule the player to act at the start
 - player.rotation is resolved.
 - 