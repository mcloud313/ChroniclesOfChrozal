#game/group.py
from __future__ import annotations
import uuid
from typing import Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .character import Character

class Group:
    """
    Represents a single adventuring party/group.
    """
    def __init__(self, leader: Character):
        """Initializes a new group with a given leader."""
        self.id: int = uuid.uuid4().int & (1<<64)-1 # Unique Id for the group
        self.leader: Character = leader
        self.members: Set[Character] = {leader}

    def add_member(self, character: Character):
        """Adds a character to the group."""
        self.members.add(character)
        character.group = self

    def remove_member(self, character: Character):
        """Removes a character from the group and handles leader promotion."""
        self.members.discard(character)
        character.group = None

        # If the leader was the one who left, promote a new leader
        if self.leader == character and self.members:
            # simple promotion: the next person in the set becomes the leader
            new_leader = next(iter(self.members))
            self.leader = new_leader

    async def disband(self):
        """Disbands the netire group, notifying all members."""
        await self.broadcast("{yThe group has been disbaned.{x")
        for member in list(self.members):
            member.group = None
        self.members.clear()

    async def broadcast(self, message: str, exclude: Optional[Set[Character]] = None):
        """Sends a message to all members of the group."""
        for member in self.members:
            if not exclude or member not in exclude:
                await member.send(message)

    def get_slowest_member_rt(self) -> float:
        """Finds the highest roundtime among all group members."""
        if not self.members:
            return 0.0
        return max(member.roundtime for member in self.members)

                
