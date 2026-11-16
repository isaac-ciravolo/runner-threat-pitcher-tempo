# G3 history validation

The verified run `897435bbc46547bd92d05fde705d8f89` contains 403,611 completed-play windows across 7,289 games (2022–2024), including 8,141 recorded attempt windows. All published artifact hashes resolve successfully.

Independent raw-response checks cover 40,788 actions, 8,731 explicit links and 9,097 eligible movement records; 4,055 movement records fall outside the risk population. Opening identity reconstruction changes 3,754 pitcher assignments and excludes an additional 5,391 rows from history contributions while retaining prediction opportunities. These exclusions prevent substitutions from contaminating runner histories.

Independent batch calculations match 5,562 history counts in 35 reference games, including resumed-game cases. Histories use strictly earlier availability and remain frozen within each runner/game. Notebook 10 was executed and its outputs reviewed.

The source checks establish feed consistency, not independent video ground truth. Release-timing annotation remains pending. The 2025 feed holdout remains closed. Older model findings remain withdrawn; the next stage reruns the unchanged model specifications on these corrected inputs, with 2024 treated as development data.
