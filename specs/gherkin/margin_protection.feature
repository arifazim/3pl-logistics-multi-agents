Feature: Margin Protection

  Scenario: Prevent quote generation under 12% margin
    Given a customer requests a quote from "Tracy" to "Fremont"
    And the cheapest vendor cost is 300.00
    When CUSTOMER_QUOTATION_AGENT calculates a customer quote
    Then the profit margin of 12% is calculated
    And the margin protection check passes

  Scenario: Escalate to Human Supervisor when margin protection fails
    Given a customer requests a quote from "Tracy" to "Fremont"
    And vendor costs would result in margin less than 12% below floor
    And no alternative vendor can offer a lower rate
    When the pricing engine fails margin protection
    Then HUMAN_SUPERVISOR must be alerted with the escalation reason "Low margin protection violation"
