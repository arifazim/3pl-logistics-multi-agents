# Spec-Driven SDLC (SDD)

## 1. Write Gherkin Specs
- Customer quotation margin protection
- Vendor quotation reliability
- SLA delivery windows
- Empty-mile reduction

## 2. Map Specs → Agents
- CUSTOMER_QUOTATION_AGENT handles pricing logic
- VENDOR_QUOTATION_AGENT handles vendor marketplace
- LOAD_PLANNING_AGENT handles routing

## 3. Map Agents → Skills
- Each agent loads only the skills needed (progressive disclosure)

## 4. Implement MCP Servers
- TMS, WMS, Vendor Directory, Rate Cards, Policy, Telemetry

## 5. Implement Agents (ADK)
- Each agent reads SKILL.md and MCP tools

## 6. Run Trajectory Tests
- End-to-end flows

## 7. Evaluate with EVALUATION_AGENT
- Margin leakage
- SLA performance
- Empty miles
- Vendor reliability

## 8. Kaizen Loop
- Update specs
- Update skills
- Re-run tests
