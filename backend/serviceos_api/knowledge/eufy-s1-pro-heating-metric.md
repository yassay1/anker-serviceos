# eufy Wearable Breast Pump S1 Pro heating battery estimates

Source ID: `eufy-s1-pro-heating-battery-v1`
Applicability: verified model `T8D04` only
Publication status: Published
Consumer visibility: Visible
Source record: user-supplied workbook, sheet `eufy Breast Pump Q&A`, entry “How much extra battery does the heating function consume on eufy Wearable Breast Pump S1 Pro(T8D04)?”

The supplied answer, marked Published/Visible in its workbook, states that heating uses approximately 10% additional battery for 5 minutes, 20% for 10 minutes (default), and 30% for 15 minutes. These are source estimates, not measurements from an individual device or an independently verified current manufacturer policy. Preserve “approximately” and do not extrapolate beyond these three durations.

Structured metric: `heating-extra-battery`; x-axis `Heating duration (minutes)`; y-axis `Additional battery use`; unit `%`; points `5:10`, `10:20`, `15:30`.

Metric ID: `heating-extra-battery`
Point: 5 minutes = 10 percent
Point: 10 minutes = 20 percent
Point: 15 minutes = 30 percent
