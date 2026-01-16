Feature: Upstream error handling
  As a client
  I want upstream errors mapped into stable responses
  So I get actionable feedback without server crashes

  Scenario: Chat completions return a structured 502 on upstream failure
    Given the upstream responses endpoint returns an error
    When I request a chat completion
    Then the response status should be 502
    And the response error payload should include the upstream error

  Scenario: Responses return a structured 502 on upstream failure
    Given the upstream responses endpoint returns an error
    When I request a response
    Then the response status should be 502
    And the response error payload should include the upstream error
