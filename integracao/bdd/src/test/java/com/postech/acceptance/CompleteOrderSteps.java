package com.postech.acceptance;
import io.cucumber.java.en.*;
import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;

/** Drives real HTTP acceptance scripts. No token signing or payment success injection. */
public class CompleteOrderSteps {
    private final Path integration = Path.of("..").toAbsolutePath().normalize();
    private final ObjectMapper json = new ObjectMapper();
    private JsonNode commercial, completed;
    private String url;
    @Given("um ambiente integrado de demonstracao explicitamente autorizado")
    public void environment() {
        assertEquals("true", System.getenv("SOAT_E2E_ENABLED"), "Set SOAT_E2E_ENABLED=true only for an isolated test environment");
        url = System.getenv().getOrDefault("SOAT_BASE_URL", "http://127.0.0.1:18080");
        var uri=java.net.URI.create(url);
        assertTrue("https".equals(uri.getScheme()) || ("http".equals(uri.getScheme()) && Set.of("127.0.0.1","localhost").contains(uri.getHost())), "HTTPS required outside localhost");
        assertTrue(Files.isRegularFile(integration.resolve(".env")), "Configure demo environment first");
    }
    @When("abro a OS diagnostico rejeito uma proposta e aprovo sua nova versao")
    public void commercialFlow() throws Exception {
        commercial = run("verify-phase3.py", "phase3-integration-results.json", 180);
        assertTrue(commercial.path("passed").asBoolean());
        assertNotEquals(commercial.path("rejectedBudgetId"), commercial.path("approvedBudgetId"));
    }
    @Then("a OS aguarda pagamento e bloqueia o reparo prematuro")
    public void waiting() {
        assertEquals("AGUARDANDO_PAGAMENTO", commercial.path("finalState").asText());
        assertTrue(commercial.path("checks").toString().contains("repair blocked before payment"));
        System.out.println("OS para pagamento real de teste: " + commercial.path("osId").asText());
        System.out.println("Obtenha o QR na API autenticada de pagamentos. Aguardando ate 15 minutos; nenhum pagamento e simulado.");
    }
    @When("o comprador paga o QR real de teste e o mecanico conclui o reparo")
    public void paymentAndRepair() throws Exception {
        completed = run("verify-phase4.py", "phase4-complete-results.json", 960,
            "--os-id", commercial.path("osId").asText(), "--action", "complete", "--deliver", "--timeout", "900");
    }
    @Then("a mesma OS e entregue com tentativa e trabalho preservados")
    public void delivered() {
        assertTrue(completed.path("passed").asBoolean());
        assertEquals("ENTREGUE", completed.path("state").asText());
        for (String field: List.of("osId","attemptId","trabalhoId")) {
            assertFalse(commercial.path(field).asText().isBlank());
            assertEquals(commercial.path(field),completed.path(field),field);
        }
    }
    private JsonNode run(String script, String report, int seconds, String... args) throws Exception {
        var command = new ArrayList<String>();
        command.add(System.getenv().getOrDefault("PYTHON", "python"));
        command.add(integration.resolve(script).toString());
        command.add("--base-url"); command.add(url); command.addAll(List.of(args));
        Path evidence = integration.resolve("evidencias").resolve(report);
        Files.deleteIfExists(evidence); // Explicit generated report, never a source/config file.
        Path log=Files.createTempFile(Path.of("target"),"acceptance-",".log");
        Process process = new ProcessBuilder(command).directory(integration.toFile()).redirectErrorStream(true).redirectOutput(log.toFile()).start();
        try {
            assertTrue(process.waitFor(seconds,TimeUnit.SECONDS), "Acceptance timeout; inspect local log " + log);
            assertEquals(0,process.exitValue(),"Acceptance failed; inspect local log " + log);
            assertTrue(Files.isRegularFile(evidence),"Missing fresh acceptance evidence");
            return json.readTree(Files.readString(evidence));
        } finally { if(process.isAlive()) process.destroyForcibly(); }
    }
}
