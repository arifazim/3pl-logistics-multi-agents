Feature: Vendor Quotation Reliability

  Scenario: Select the most reliable vendor
    Given a list of available vendors for route "Tracy" to "Fremont"
    And vendor "V002" has reliability score 95 and cost 320.00
    And vendor "V001" has reliability score 92 and cost 300.00
    When VENDOR_QUOTATION_AGENT compares vendor quotes
    Then vendor "V002" is preferred due to higher reliability score despite slightly higher cost
    And vendor "V002" is selected for route planning
