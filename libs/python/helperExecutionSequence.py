from anytree import Node


def getAppSubscriptionByName(name, btpUsecase):
    for appSubscription in btpUsecase.definedAppSubscriptions:
        if name == appSubscription.name:
            return appSubscription
    return None


def getServiceByName(name, btpUsecase):
    for service in btpUsecase.definedServices:
        if name == service.name:
            return service
    return None


def getChildrenForItem(item, btpUsecase, tree):

    service = item.name
    parentService = mapNodeToService(service, tree)
    children = []
    if service.requiredApplications and service.requiredApplications is not None and len(service.requiredApplications) > 0:
        for thisDependency in service.requiredApplications:
            thisAppSubscription = getAppSubscriptionByName(thisDependency, btpUsecase)
            child = mapNodeToService(thisAppSubscription, tree)
            child.parent = parentService
            children.append(child)

    if service.requiredServices and service.requiredServices is not None and len(service.requiredServices) > 0:
        children = []
        for thisDependency in service.requiredServices:
            thisService = getServiceByName(thisDependency, btpUsecase)
            child = mapNodeToService(thisService, tree)
            child.parent = parentService
            children.append(child)

    return children


def getParentForItem(item, btpUsecase):

    serviceToCheck = item.name
    parent = None

    for appSubscription in btpUsecase.definedAppSubscriptions:
        for thisDependency in appSubscription.requiredApplications:
            if thisDependency == serviceToCheck.name:
                return appSubscription
        for thisDependency in appSubscription.requiredServices:
            if thisDependency == serviceToCheck.name:
                return appSubscription

    for service in btpUsecase.definedServices:
        for thisDependency in service.requiredApplications:
            if thisDependency == serviceToCheck.name:
                return service
        for thisDependency in service.requiredServices:
            if thisDependency == serviceToCheck.name:
                return service
    return parent


def mapNodeToService(service, tree):
    for item in tree:
        thisService = item.name
        if service == thisService:
            return item
    return None


def buildDependencyTree(btpUsecase):

    allServicesAndApps = []
    result = []

    # Parse all app subscriptions defined in the use case file
    for thisService in btpUsecase.definedAppSubscriptions:
        allServicesAndApps.append(Node(thisService))

    # Parse all services defined in the use case file
    for thisService in btpUsecase.definedServices:
        allServicesAndApps.append(Node(thisService))

    for item in allServicesAndApps:
        parentService = getParentForItem(item, btpUsecase)
        parentNode = mapNodeToService(parentService, allServicesAndApps)
        children = getChildrenForItem(item, btpUsecase, allServicesAndApps)
        if children:
            item.children = children
        if parentNode:
            item.parent = parentNode

    # Now only add those nodes that don't have any parents
    # as they have all potential children elements
    for item in allServicesAndApps:
        if not item.parent:
            result.append(item)

    return result
