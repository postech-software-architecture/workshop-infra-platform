package com.postech.acceptance;
import org.junit.platform.suite.api.*;
import io.cucumber.junit.platform.engine.Constants;
@Suite @IncludeEngines("cucumber") @SelectClasspathResource("features")
@ConfigurationParameter(key=Constants.GLUE_PROPERTY_NAME,value="com.postech.acceptance")
@ConfigurationParameter(key=Constants.PLUGIN_PROPERTY_NAME,value="pretty,json:target/cucumber.json,html:target/cucumber.html")
public class CompleteOrderTest {}
