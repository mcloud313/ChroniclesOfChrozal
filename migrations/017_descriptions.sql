UPDATE races SET description=CASE name
 WHEN 'Chrozalin' THEN 'Adaptable human folk whose diverse communities span the Valian Coast, inland kingdoms, and distant roads.'
 WHEN 'Dwarf' THEN 'Broad, enduring mountain folk whose braided traditions preserve the songs of stone, craft, and kinship.'
 WHEN 'Elf' THEN 'Long-lived folk of forest and hidden citadel, with keen senses and an enduring affinity for arcane lore.'
 WHEN 'Yan-tar' THEN 'Ancient shell-bearing folk who carry their histories in patient speech, patterned shells, and sacred pilgrimages.'
 WHEN 'Grak' THEN 'Towering, tusked folk with immense physical strength and rich traditions of clan honor and oral history.' END
 WHERE (name,description) IN (('Chrozalin','Versatile humans...'),('Dwarf','Stout mountain folk...'),('Elf','Graceful forest dwellers...'),('Yan-tar','Ancient turtle-like people...'),('Grak','Towering humanoids...'));
UPDATE rooms SET description=replace(description,'Read relics, then attune starmap fragment.','The dormant star-rings hint at mysteries reserved for much more experienced adventurers.') WHERE description LIKE '%Read relics, then attune starmap fragment.%';
