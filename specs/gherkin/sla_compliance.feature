Feature: SLA Compliance

  Scenario: Validate delivery constraints
    Given shipment routes
    When compliance check runs
    Then violations are flagged within 24 hours
    And mitigation is suggested

  Scenario: SLA threshold configuration
    Given standard delivery window is 72 hours
    And express delivery window is 36 hours
    When compliance checks run
    Then violations are flagged for shipments exceeding within 24 hours threshold