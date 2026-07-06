Feature: Load Planning

Scenario: Optimize vehicle allocation
  Given multiple shipments and limited fleet
  When load planner runs
  Then shipments are grouped optimally
  And vehicle utilization is maximized