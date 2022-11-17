from libs.python.helperServiceInstances import createServiceInstance, setInstanceNames
from libs.python.helperExecutionSequence import buildDependencyTree, ExecutionStatus
import logging
from libs.python.helperCommandExecution import runCommandAndGetJsonResult, runShellCommand, runShellCommandFlex
from libs.python.helperJson import dictToString, convertStringToJson, addKeyValuePair
from libs.python.helperServiceInstances import checkIfAllServiceInstancesCreated
from libs.python.helperServices import BTPSERVICEEncoder
from libs.python.helperEnvCF import get_cf_service_status
from libs.python.helperEnvKyma import get_kyma_service_status
from libs.python.helperEnvBTP import get_btp_service_status

import sys
import os
import time
import json

log = logging.getLogger(__name__)


def createServiceInstancesAndAppSubscriptions(btpUsecase):
    log.header("Initiate subscription to apps and creation of service instances")

    # Ensure proper handling of service instance names
    if btpUsecase.definedServices:
        setInstanceNames(btpUsecase)

    serviceDependencyTree = buildDependencyTree(btpUsecase)

    current_time = 0
    usecaseTimeout = btpUsecase.repeatstatustimeout
    search_every_x_seconds = btpUsecase.repeatstatusrequest
    # Wait until thisService has been created and is available
    while usecaseTimeout > current_time:
        # Execute the creation of app subscriptions and service intances
        for item in serviceDependencyTree:
            for descendant in item.descendants:
                thisService = descendant.name

                if canTriggerServiceCreation(btpUsecase, thisService, serviceDependencyTree):

                    # Initiate the app subscriptions
                    if thisService.category == "APPLICATION":
                        if thisService.entitleonly is False:
                            subscribe_app_to_subaccount(btpUsecase, thisService)

                    # Initiate the creationg of the service instance
                    if thisService.category == "SERVICE" or thisService.category == "ELASTIC_SERVICE":
                        if thisService.entitleonly is False:
                            createServiceInstance(btpUsecase, thisService, thisService.targetenvironment, thisService.category)
        time.sleep(search_every_x_seconds)
        current_time += search_every_x_seconds

    log.header("Initiated subscription to apps and creation of service instances")


def subscribe_app_to_subaccount(btpUsecase, appSubscription):
    accountMetadata = btpUsecase.accountMetadata
    subaccountid = accountMetadata["subaccountid"]

    app = appSubscription.name
    plan = appSubscription.plan
    parameters = appSubscription.parameters

    command = "btp subscribe accounts/subaccount \
    --subaccount '" + subaccountid + "' \
    --to-app '" + app + "'"

    if plan is not None:
        # For custom apps a plan can be none - this is safeguarded when checking if account is capable of usecase
        command = command + " --plan '" + plan + "'"

    # add parameters in case they are provided for the app subscription
    if parameters:
        command = command + " --parameters '" + dictToString(parameters) + "'"

    isAlreadySubscribed = checkIfAppIsSubscribed(btpUsecase, app, plan)
    if isAlreadySubscribed is False:
        message = "subscribe sub account to >" + app + "<"

        if plan is not None:
            # (Optional) The subscription plan of the multitenant application. You can omit this parameter if the multitenant application is in the current global account.
            message = message + " and plan >" + plan + "<"

        runShellCommand(btpUsecase, command, "INFO", message)
        appSubscription.executionStatus = ExecutionStatus.TRIGGERED
    else:

        message = "subscription already there for >" + app + "<"
        if plan is not None:
            # (Optional) The subscription plan of the multitenant application. You can omit this parameter if the multitenant application is in the current global account.
            message = message + " and plan >" + plan + "<"
        appSubscription.executionStatus = ExecutionStatus.AVAILABLE

        log.info(message)


def checkIfAppIsSubscribed(btpUsecase, appName, appPlan):
    result = False
    accountMetadata = btpUsecase.accountMetadata
    subaccountid = accountMetadata["subaccountid"]

    command = "btp --format json get accounts/subscription --subaccount '" + \
        subaccountid + "' --of-app '" + appName + "'"

    if appPlan is not None:
        # (Optional) The subscription plan of the multitenant application. You can omit this parameter if the multitenant application is in the current global account.
        command = command + " --plan '" + appPlan + "'"

    resultCommand = runCommandAndGetJsonResult(
        btpUsecase, command, "INFO", "check if app already subscribed")

    if "state" in resultCommand and resultCommand["state"] == "SUBSCRIBED":
        result = True

    return result


def get_subscription_status(btpUsecase, app):
    accountMetadata = btpUsecase.accountMetadata

    app_name = app.name
    app_plan = app.plan
    subaccountid = accountMetadata["subaccountid"]

    command = "btp --format json list accounts/subscription --subaccount '" + subaccountid + "'"
    message = "subscription status of >" + app_name + "<"
    p = runShellCommand(btpUsecase, command, "CHECK", message)
    result = p.stdout.decode()
    result = convertStringToJson(result)

    for application in result["applications"]:
        thisAppName = application["appName"]
        thisAppPlan = application["planName"]
        if (thisAppName == app_name and thisAppPlan == app_plan):
            return application

    log.error("COULD NOT FIND SUBSCRIPTON TO >" +
              app_name + "< and plan >" + app_plan + "<")
    sys.exit(os.EX_DATAERR)


def get_subscription_deletion_status(btpUsecase, app):
    accountMetadata = btpUsecase.accountMetadata

    app_name = app["name"]
    app_plan = app["plan"]
    subaccountid = accountMetadata["subaccountid"]

    command = "btp --format json list accounts/subscription --subaccount '" + subaccountid + "'"
    message = "subscription status of >" + app_name + "<"
    p = runShellCommandFlex(btpUsecase, command,
                            "CHECK", message, False, False)
    result = p.stdout.decode()
    result = convertStringToJson(result)

    for application in result["applications"]:
        thisAppName = application["appName"]
        thisAppPlan = application["planName"]
        status = application["state"]
        if (thisAppName == app_name and thisAppPlan == app_plan):
            if status == "NOT_SUBSCRIBED":
                return "deleted"
            if status == "UNSUBSCRIBE_FAILED":
                return "UNSUBSCRIBE_FAILED"
    return "not deleted"


def checkIfAllSubscriptionsAreAvailable(btpUsecase):
    command = "btp --format json list accounts/subscription --subaccount '" + \
        btpUsecase.subaccountid + "'"
    resultCommand = runCommandAndGetJsonResult(
        btpUsecase, command, "INFO", "check status of app subscriptions")

    allSubscriptionsAvailable = True
    for app in btpUsecase.definedAppSubscriptions:

        if app.entitleonly is False:

            for thisJson in resultCommand["applications"]:
                name = thisJson.get("appName")
                plan = thisJson.get("planName")
                status = thisJson.get("state")
                tenantId = thisJson.get("tenantId")

                if app.name == name and app.plan == plan and app.successInfoShown is False:
                    if status == "SUBSCRIBE_FAILED":
                        log.error(
                            "BTP account reported that subscription on >" + app.name + "< has failed.")
                        sys.exit(os.EX_DATAERR)

                    if status != "SUBSCRIBED":
                        allSubscriptionsAvailable = False
                        app.status = status
                        app.successInfoShown = False
                        app.statusResponse = thisJson
                    else:
                        message = "subscription to app >" + app.name + "<"
                        if plan is not None:
                            message = message + " (plan " + app.plan + ") is now available"
                        log.success(message)
                        app.tenantId = tenantId
                        app.successInfoShown = True
                        app.statusResponse = thisJson
                        app.status = "SUBSCRIBED"

    return allSubscriptionsAvailable


def determineTimeToFetchStatusUpdates(btpUsecase):
    maxTiming = int(btpUsecase.repeatstatusrequest)

    for service in btpUsecase.definedServices:
        status = service.status
        if service.repeatstatusrequest is not None:
            repeatstatusrequest = service.repeatstatusrequest
            if repeatstatusrequest > maxTiming and status != "create succeeded":
                maxTiming = repeatstatusrequest

    return maxTiming


def track_creation_of_subscriptions_and_services(btpUsecase):
    accountMetadata = btpUsecase.accountMetadata

    current_time = 0

    usecaseTimeout = btpUsecase.repeatstatustimeout
    while usecaseTimeout > current_time:
        areAllInstancesCreated = True
        areAllSubscriptionsCreated = True

        search_every_x_seconds = determineTimeToFetchStatusUpdates(btpUsecase)

        if len(btpUsecase.definedServices) > 0:
            areAllInstancesCreated = checkIfAllServiceInstancesCreated(
                btpUsecase, search_every_x_seconds)

        if len(btpUsecase.definedAppSubscriptions) > 0:
            areAllSubscriptionsCreated = checkIfAllSubscriptionsAreAvailable(
                btpUsecase)

        if (areAllInstancesCreated is True and areAllSubscriptionsCreated is True):
            log.success(
                "All service instances and subscriptions are now available".upper())
            accountMetadata = addCreatedServicesToMetadata(btpUsecase)
            return accountMetadata

        time.sleep(search_every_x_seconds)
        current_time += search_every_x_seconds

    log.error(
        "Could not get all services and/or app subscriptions up and running. Sorry.")


def try_until_done(btpUsecase, command, message, key, value, search_every_x_seconds, timeout_after_x_seconds):
    result = "ERROR"

    current_time = 0
    number_of_tries = 0

    while timeout_after_x_seconds > current_time:
        number_of_tries += 1
        checkMessage = message + " (try " + str(number_of_tries) + \
            " - trying again in " + str(search_every_x_seconds) + "s)"
        result = runCommandAndGetJsonResult(
            btpUsecase, command, "CHECK", checkMessage)
        status = result[key]
        if status == value:
            return "DONE"
        time.sleep(search_every_x_seconds)
        current_time += search_every_x_seconds

    return result


def addCreatedServicesToMetadata(btpUsecase):
    accountMetadata = btpUsecase.accountMetadata

    if "createdServiceInstances" not in accountMetadata:
        accountMetadata = addKeyValuePair(
            accountMetadata, "createdServiceInstances", [])

    if "createdAppSubscriptions" not in accountMetadata:
        accountMetadata = addKeyValuePair(
            accountMetadata, "createdAppSubscriptions", [])

    if len(btpUsecase.definedAppSubscriptions) > 0:
        for service in btpUsecase.definedAppSubscriptions:
            thisService = convertStringToJson(json.dumps(
                service, indent=4, cls=BTPSERVICEEncoder))
            accountMetadata["createdAppSubscriptions"].append(thisService)

    if len(btpUsecase.definedServices) > 0:
        for service in btpUsecase.definedServices:
            thisService = convertStringToJson(json.dumps(
                service, indent=4, cls=BTPSERVICEEncoder))
            accountMetadata["createdServiceInstances"].append(thisService)

    return accountMetadata


def get_service_status(btpUsecase, service, targetEnvironment):
    status = None

    if targetEnvironment == "cloudfoundry":
        [servicebroker, status] = get_cf_service_status(btpUsecase, service)
    elif targetEnvironment == "kymaruntime":
        status = get_kyma_service_status(btpUsecase, service)
    elif targetEnvironment == "sapbtp":
        status = get_btp_service_status(btpUsecase, service)
    else:
        log.error(
            "The targetenvironment is not supported ")
        sys.exit(os.EX_DATAERR)

    return status


def canTriggerServiceCreation(btpUsecase, service, executionTree):

    for item in executionTree:
        for descendant in item.descendants:
            thisService = descendant.name
            if service == thisService:
                children = descendant.children
                for child in children:
                    childService = child.name
                    status = get_service_status(btpUsecase, thisService, thisService.targetenvironment)

                    if childService.executionStatus != ExecutionStatus.AVAILABLE:
                        return False
                return True
    return False
