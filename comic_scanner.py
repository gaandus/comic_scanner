#!python

import urllib, urllib2, cookielib
from urllib2 import URLError
import ConfigParser
import smtplib
from smtplib import SMTPException
from datetime import datetime
import time
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ElementTree
import lxml.html
from os.path import abspath
from os.path import isfile

VERSION = "2.0"

config = ConfigParser.RawConfigParser()
config.read('config.cfg')
SMTP_FROM_ADDRESS = config.get('SMTP', 'SMTP_FROM_ADDRESS')
SMTP_TO_ADDRESS = config.get('SMTP', 'SMTP_TO_ADDRESS')
SMTP_HOST = config.get('SMTP', 'SMTP_HOST')
SMTP_PORT = config.get('SMTP', 'SMTP_PORT')
SMTP_USERNAME = config.get('SMTP', 'SMTP_USERNAME')
SMTP_PASSWORD = config.get('SMTP', 'SMTP_PASSWORD')

# Anonymized URLs
COMIC_SITE_LOGIN_URL = config.get('GENERAL', 'COMIC_SITE_LOGIN_URL')
COMIC_SITE_WANT_LIST_URL = config.get('GENERAL', 'COMIC_SITE_WANT_LIST_URL')
COMIC_SITE_ADD_TO_CART_URL = config.get('GENERAL', 'COMIC_SITE_ADD_TO_CART_URL')
COMIC_SITE_USER_NAME = config.get('GENERAL', 'COMIC_SITE_USER_NAME')
COMIC_SITE_PASSWORD = config.get('GENERAL', 'COMIC_SITE_PASSWORD')

CHECK_INTERVAL_SECONDS = config.getfloat('GENERAL', 'CHECK_INTERVAL_SECONDS')

SEND_NOTIFICATIONS = config.getboolean('GENERAL', 'SEND_NOTIFICATIONS')
AUTO_ADD_TO_CART = config.getboolean('GENERAL', 'AUTO_ADD_TO_CART')

ITEM_MESSAGE_EXCLUDE_FILTERS = config.get('GENERAL', 'ITEM_MESSAGE_EXCLUDE_FILTERS')

errorOccurred = False
errorMsg = ""
URLErrorCount = 0
SMTPErrorCount = 0
opener = False
cj = False

class Item:
    def __init__(self):
        pass

    title = ""
    itemId = ""
    price = ""

def logIn():
    global cj
    global opener

    if opener is False:
        print "Logging in as " + COMIC_SITE_USER_NAME
        cj = cookielib.CookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        login_data = urllib.urlencode({'CustomerEmail': COMIC_SITE_USER_NAME, 'CustomerPassword': COMIC_SITE_PASSWORD})
        resp = opener.open(COMIC_SITE_LOGIN_URL, login_data)
        if resp.code != 200:
            raise Exception('Login request returned error code ' + resp.code)

        content = resp.read()
        if content.find("<title>Comic Books - Log In</title>") != -1:
            raise Exception("Invalid login. Check COMIC_SITE_USER_NAME and COMIC_SITE_PASSWORD in config.cfg")

        print "Login successful"

def logOut():
    print "Logging out"
    global cj
    global opener
    opener = False
    cj = False

def doCheck():
    global errorOccurred
    global errorMsg
    global URLErrorCount
    global SMTPErrorCount
    global opener

    ts = datetime.now()
    print ts.strftime("%Y-%m-%d %H:%M:%S") + " Doing check..."

    try:
        logIn()

        items = parseWantList()
        cachedItems = getCachedItems()
        cacheOnly = False
        if len(cachedItems) == 0:
            print "Building cache"
            cacheOnly = True

        for item in items:
            itemCached = False
            for cachedItem in cachedItems:
                if cachedItem.itemId == item.itemId:
                    itemCached = True

            if itemCached is False:
                if cacheOnly is True:
                    msg = "Found item: "
                else:
                    msg = "New item available: "
                msg += item.title + ", $" + item.price
                print msg

                if AUTO_ADD_TO_CART is True and cacheOnly is False:
                    resp = opener.open(COMIC_SITE_ADD_TO_CART_URL + "AddItemID=" + item.itemId)
                    if resp.code != 200:
                        raise Exception('Add to cart request returned error code ' + resp.code)
                    print "Item added to cart"

                    if SEND_NOTIFICATIONS is True:
                        notice = "Item Added to cart: " + item.title + "\n\nhttps://www.example-comic-site.com/cart"
                        sendNotification(notice)

        logOut()
        saveCache(items)
    except URLError as e:
        URLErrorCount += 1
        print "Connection with " + COMIC_SITE_WANT_LIST_URL + " failed " + str(URLErrorCount) + " times. Will try again in " + str(CHECK_INTERVAL_SECONDS) + " seconds."
    except SMTPException as e:
        print "An error occurred sending notification. Check SMTP properties in config.cfg. Error: " + e.smtp_error
    except Exception as e:
        errorMsg = str(e)
        errorOccurred = True
        print errorMsg

    ts = datetime.now()
    print ts.strftime("%Y-%m-%d %H:%M:%S") + " Done with check"

    return

def saveCache(items):
    rootEl = Element("items")
    for item in items:
        itemEl = Element("item")
        itemEl.set("title", item.title)
        itemEl.set("itemId", item.itemId)
        itemEl.set("price", item.price)
        rootEl.append(itemEl)

    if isfile("item_cache.xml") is False:
        cacheFile = open("item_cache.xml", 'w')
        cacheFile.write("<items></items>")
        cacheFile.close()

    ElementTree(rootEl).write("item_cache.xml")

    return

def getCachedItems():
    items = []

    if isfile("item_cache.xml") is False:
        return items

    et = ElementTree()
    tree = et.parse(abspath("item_cache.xml"))
    xmlItems = tree.findall("item")
    for xmlItem in xmlItems:
        item = Item()
        item.title = xmlItem.get("title")
        item.itemId = xmlItem.get("itemId")
        item.price = xmlItem.get("price")
        items.append(item)

    return items

def sendNotification(text):
    notice = "From: " + SMTP_FROM_ADDRESS + "\r\nTo: " + SMTP_TO_ADDRESS + "\r\n\r\n"
    notice += text

    print "Sending notification..."

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        #server.set_debuglevel(1)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM_ADDRESS, SMTP_TO_ADDRESS, notice)
        server.quit()
    except Exception as e:
        print "Error sending notification: " + str(e)

    return

def parseWantList():
    global opener

    print "Scanning want list"

    page = 1
    nextTag = "<li class=\"next\">"
    nextPos = 0

    issues = []

    while nextPos != -1:
        resp = opener.open(COMIC_SITE_WANT_LIST_URL + "p=" + str(page))
        if resp.code != 200:
            raise Exception('Loading want list returned error code ' + resp.code)
        thisPageContent = resp.read()
        html = lxml.html.fromstring(thisPageContent)
        if thisPageContent.find("<title>Comic Books - Log In</title>") != -1:
            raise Exception("Invalid login. Check COMIC_SITE_USER_NAME and COMIC_SITE_PASSWORD in config.cfg.")

        thisPageIssues = html.find_class('issue')
        filters = ITEM_MESSAGE_EXCLUDE_FILTERS.split(',')
        for issue in thisPageIssues:
            thisIssueItems = issue.cssselect('table[class="issuestock"] td')
            for thisItem in thisIssueItems:
                # Ignore auction items
                if len(thisItem.cssselect('a[title="View Auction"]')) > 0:
                    continue

                # Apply filters
                cartMsg = thisItem.cssselect('.cartmsg')[0].text_content()
                cartMsgs = thisItem.cssselect('li')
                for msg in cartMsgs:
                    cartMsg += msg.text_content() + "\n"

                filterOut = False
                for f in filters:
                    if len(cartMsg) > 0:
                        find = cartMsg.find(f)
                        if find != -1:
                            filterOut = True
                            break
                if filterOut is True:
                    continue

                try:
                    item = Item()
                    item.title = thisItem.cssselect('meta[itemprop="name"]')[0].attrib['content']
                    item.itemId = thisItem.cssselect('meta[itemprop="sku"]')[0].attrib['content']
                    item.price = thisItem.cssselect('meta[itemprop="price"]')[0].attrib['content']

                    issues.append(item)
                except IndexError as e:
                    print "Item found but it's missing data. Skipping."

        nextPos = thisPageContent.find(nextTag)
        if nextPos != -1:
            page += 1
        else:
            break

    print "Found " + str(len(issues)) + " issue(s)."
    return issues

def main():
    print "Comic Availability Scanner v" + VERSION
    print "Checking for new issues every " + str(CHECK_INTERVAL_SECONDS) + " seconds..."

    while errorOccurred is False:
        doCheck()
        time.sleep(CHECK_INTERVAL_SECONDS)

    print errorMsg
    print "Exiting..."

if __name__ == "__main__":
    main() 