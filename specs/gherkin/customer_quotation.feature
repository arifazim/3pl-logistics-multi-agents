Feature: Customer quotation margin protection

Scenario: Quote origin → destination with vendor marketplace
  Given a customer requests a quote 
  And vendor quotes fluctuate by ±15%
  When CUSTOMER_QUOTATION_AGENT generates a quote
  Then margin must remain ≥ 12%
  And HUMAN_SUPERVISOR must approve
