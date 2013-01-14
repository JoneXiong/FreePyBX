require "luasql.postgres"

--[[
    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was with this
    file, You can obtain one at http://mozilla.org/MPL/2.0/.not distributed

    Software distributed under the License is distributed on an "AS IS"
    basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
    License for the specific language governing rights and limitations
    under the License.

    The Original Code is PythonPBX/VoiceWARE.

    The Initial Developer of the Original Code is Noel Morgan,
    Copyright (c) 2011-2012 VoiceWARE Communications, Inc. All Rights Reserved.

    http://www.vwci.com/

    You may not remove or alter the substance of any license notices (including
    copyright notices, patent notices, disclaimers of warranty, or limitations
    of liability) contained within the Source Code Form of the Covered Software,
    except that You may alter any license notices to the extent required to
    remedy known factual inaccuracies.
]]--

digits = digits or ""
gateway = gateway or nil

env = assert(luasql.postgres())
con = assert(env:connect("dbname=freepybx user=freepybx password=secretpass1 host=127.0.0.1"))
session:set_tts_parms("cepstral", "Allison")

--[[ Custom Logging makes it easier to troubleshoot or remove.]]--
function log(logval)
    freeswitch.consoleLog("NOTICE", "LUA ROUTE.LUA ----------------->" .. tostring(logval) .. "<------------- \n")
end

--[[ rows iterator object ]]--
function rows(sql)
    local cursor = assert (con:execute (sql))
    return function ()
        return cursor:fetch()
    end
end

--[[ Tidy-up connections. ]]--
function session_hangup_hook()
    freeswitch.consoleLog("NOTICE", "Session hangup hook...\n")
    con:close()
end

--[[ String "startswith" helper function. ]]--
function startswith(sbig, slittle)
    if type(slittle) == "table" then
        for k,v in ipairs(slittle) do
            if string.sub(sbig, 1, string.len(v)) == v then
                return true
            end
        end
        return false
    end
    return string.sub(sbig, 1, string.len(slittle)) == slittle
end

--[[ Split helper function. ]]--
function split(str, pat)
    local t = {}
    local fpat = "(.-)" .. pat
    local last_end = 1
    local s, e, cap = str:find(fpat, 1)
    while s do
        if s ~= 1 or cap ~= "" then
            table.insert(t,cap)
        end
        last_end = e+1
        s, e, cap = str:find(fpat, last_end)
    end
    if last_end <= #str then
        cap = str:sub(last_end)
        table.insert(t, cap)
    end
    return t
end

--[[ DTMF Key Press ]]--
function key_press(session, input_type, data, args)
    if input_type == "dtmf" then
        digits = tostring(data['digit'])
        digits = digits .. session:getDigits(3, "", 2000, 3000)
        io.write("digit: [" .. data['digit'] .. "]\nduration: [" .. data['duration'] .. "]\n")
        freeswitch.consoleLog("info", "Key pressed: " .. data["digit"])
        return "break"
    else
        io.write(data:serialize("xml"))
        e = freeswitch.Event("message")
        e:add_body("you said " .. data:get_body())
        session:sendEvent(e)
    end
end

--[[ Check blacklist for CID. ]]--
function blacklisted(num, context)
    db = assert(con:execute(string.format("SELECT * " ..
            "FROM pbx_blacklisted_numbers " ..
            "WHERE context= '%s' " ..
            "AND cid_number ='%s'", context, tostring(num))))
    if db:numrows() > 0 then
        return true
    else
        return false
    end
end

--[[ Check CID Routes ]]--
function get_cid_route(num, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_caller_id_routes " ..
            "WHERE context= '%s' AND cid_number ='%s'",
        context, tostring(num))))
    local cid_route = db:fetch({}, "a")
    if db:numrows() > 0 then
        send_route(get_route_by_id(cid_route["pbx_route_id"]), context)
    else
        return false
    end
    return true
end

--[[ DID route lookup. ]]--
function get_route_by_did(did)
    db = assert(con:execute(string.format("SELECT pbx_routes.* " ..
            "FROM pbx_routes " ..
            "INNER JOIN pbx_dids ON pbx_routes.id = pbx_dids.pbx_route_id " ..
            "WHERE pbx_dids.did = '%s'", tostring(did))))
    return db:fetch({}, "a")
end

--[[ Virtual mailbox route. ]]--
function get_virtual_mailbox(route, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_virtual_mailboxes WHERE extension= '%s' AND context ='%s'",
        route["name"], context)))
    return db:fetch({}, "a")
end

--[[ Interestingly, the voicemail profile info carries over from the directory with the email logic. ]]--
function do_virtual_mailbox(route,context)
    local vmb = get_virtual_mailbox(route, context)

    if vmb["skip_greeting"] == "t" then
        log("skip greeting")
        session:execute("set", "skip_greeting=true")
    end

    if vmb["audio_file"] ~= nil then
        log("has audio file")
        local audio
        for k,v in pairs(split(vmb["audio_file"],",")) do
            audio = v
        end

        session:execute("playback", "${base_dir}/htdocs/vm/" .. context .. "/recordings/" .. audio)
    end

    session:execute("voicemail", profile .. " ".. context .. " " .. route["name"])
end

--[[ ID route lookup. ]]--
function get_route_by_id(id)
    db = assert(con:execute(string.format("SELECT * FROM pbx_routes WHERE id = %d", tonumber(id))))
    return db:fetch({}, "a")
end

--[[ Hard limit. ]]--
function get_inbound_channel_limit(id)
    db = assert(con:execute(string.format("SELECT hard_channel_limit FROM customers WHERE id = %d", tonumber(id))))
    return db:fetch({}, "a")
end

--[[ In limit. ]]--
function get_inbound_channel_limit(id)
    db = assert(con:execute(string.format("SELECT inbound_channel_limit FROM customers WHERE id = %d", tonumber(id))))
    return db:fetch({}, "a")
end

--[[ Out limit. ]]--
function get_outbound_channel_limit(id)
    db = assert(con:execute(string.format("SELECT outbound_channel_limit FROM customers WHERE id = %d", tonumber(id))))
    return db:fetch({}, "a")
end

--[[ get customer ]]--
function get_customer_by_did(did)
    db = assert(con:execute(string.format("SELECT * FROM pbx_dids d INNER JOIN customers c ON c.id = d.customer_id WHERE did = '%s'" , did)))
    return db:fetch({}, "a")
end

--[[ get customer ]]--
function get_customer_by_id(id)
    db = assert(con:execute(string.format("SELECT * FROM customers WHERE id = %d" , tonumber(id))))
    return db:fetch({}, "a")
end

--[[ get dids ]]--
function get_dids_by_customer_id(id)
    db = assert(con:execute(string.format("SELECT did FROM pbx_dids d INNER JOIN customers c ON c.id = d.customer_id WHERE customer_id = %d" , id)))
    return db:fetch({}, "a")
end

--[[ get channel count ]]--
function get_channel_count_by_did(did)
    db = assert(con:execute(string.format("SELECT count(*) AS channel_count from channels WHERE dest = '%s'" , tostring(did))))
    return db:fetch({}, "a")
end

--[[ get outbound channel count ]]--
function get_outbound_channel_count_by_context(context)
    local db = assert(con:execute(string.format("SELECT count(*) AS channel_count from channels WHERE context = '%s' AND direction = 'outbound'" , context)))
    return db:fetch({}, "a")
end

--[[ Call Center Queue lookup. ]]--
function get_cc(name, context)
    db = assert(con:execute(string.format("SELECT * FROM call_center_queues WHERE name = '%s' AND context = '%s'",
        name, context)))
    return db:fetch({}, "a")
end

--[[ Call Center position. ]]--
function get_cc_position(name)
    db = assert(con:execute(string.format("SELECT count(*) AS num FROM call_center_callers WHERE queue = '%s'", name)))
    return db:fetch({}, "a")
end

--[[ Call Center Agent Tier count. ]]--
function get_cc_tier_agents(name)
    db = assert(con:execute(string.format("SELECT count(*) AS agent_num FROM call_center_tiers WHERE queue = '%s'",
        name)))
    return db:fetch({}, "a")
end

--[[ Call Center logic. ]]--
function do_cc(name, context)
    local cc = get_cc(name, context)
    local ccp = get_cc_position(name)
    local cc_agents = get_cc_tier_agents(name)
    local hold_time = tonumber(ccp["num"]) * tonumber(cc["approx_hold_time"])

    if (hold_time > 0) then
        hold_time = hold_time/tonumber(cc_agents["agent_num"])
    end

    log("agent num" .. cc_agents["agent_num"])

    local cc_num = tonumber(ccp["num"])+1

    session:sleep(2000)
    if cc["audio_type"] == "1" then
        session:execute("playback", "${base_dir}/htdocs/vm/".. context .."/recordings/" .. cc["audio_name"])
    else
        local tts = get_tts_by_id(cc["audio_name"], context)
        session:set_tts_parms("cepstral", tts["voice"])
        session:speak(tts["text"])
    end

    session:sleep(2000)
    log(cc["announce_position"])

    if (cc["announce_position"]=="t") then
        session:execute("playback","ivr/ivr-you_are_number.wav")
        session:speak(tostring(cc_num))
        session:execute("playback","ivr/ivr-in_line.wav")
        session:speak("Your estimated hold time is " .. tostring(hold_time)  .. " minutes.")
    end

    session:execute("callcenter", name .. "@" .. context)
end

--[[ Group Lookup. ]]--
function get_group(name, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_groups WHERE name = '%s' AND context = '%s'",
        name, context)))
    return db:fetch({}, "a")
end
--[[ Text to Speech lookup. ]]--
function get_tts_by_id(name, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_tts WHERE id = %d AND context = '%s'",
        tonumber(name), context)))
    return db:fetch({}, "a")
end

function get_route_by_ext(ext,context)
    log(ext)
    db = assert(con:execute(string.format("SELECT * FROM pbx_routes WHERE name = '%s' AND context = '%s'",
        tostring(ext), context)))
    return db:fetch({}, "a")
end

function get_route_by_ivr_opt(option, id)
    db = assert(con:execute(string.format("SELECT * FROM pbx_routes "..
            "INNER JOIN pbx_ivr_options " ..
            "ON pbx_routes.id = pbx_ivr_options.pbx_route_id " ..
            "WHERE pbx_ivr_options.option ='%s' " ..
            "AND pbx_ivr_options.pbx_ivr_id=%d", option, tonumber(id))))
    return db:fetch({}, "a")
end

function get_virtual_extension(route, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_virtual_extensions " ..
            "WHERE extension= '%s' " ..
            "AND context ='%s'", route["name"], context)))
    return db:fetch({}, "a")
end

function get_virtual_mailbox(route, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_virtual_mailboxes WHERE extension= '%s' AND context ='%s'",
        route["name"], context)))
    return db:fetch({}, "a")
end

function get_default_gateway(context)
    db = assert(con:execute(string.format("SELECT default_gateway FROM customers WHERE context = '%s'", context)))
    return db:fetch({}, "a")
end

function get_extension(extension, context)
    db = assert(con:execute(string.format("SELECT pbx_endpoints.*, customers.id AS customer_id "..
            "FROM pbx_endpoints "..
            "INNER JOIN customers "..
            "ON pbx_endpoints.user_context = customers.context "..
            "WHERE auth_id= '%s' "..
            "AND user_context ='%s'", extension, context)))
    return db:fetch({}, "a")
end

function get_ivr(route,context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_ivrs WHERE context= '%s' AND name ='%s'",
        context, route["name"])))
    return db:fetch({}, "a")
end

function get_tts(route,context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_tts WHERE context = '%s' AND id = %d",
        context, tonumber(route["data"]))))
    return db:fetch({}, "a")
end

function get_outbound_caller_id(user_name, context)
    db = assert(con:execute(string.format("SELECT pbx_endpoints.outbound_caller_id_name AS ext_name, "..
            "pbx_endpoints.outbound_caller_id_number AS ext_number, pbx_endpoints.user_id AS user_id, " ..
            "customers.tel AS tel, customers.name AS customer_name, customers.default_gateway AS gateway, "..
            "customers.id AS customer_id "..
            "FROM pbx_endpoints "..
            "INNER JOIN customers ON pbx_endpoints.user_context = customers.context "..
            "WHERE customers.context= '%s' AND pbx_endpoints.auth_id ='%s'", context, user_name)))
    return db:fetch({}, "a")
end

function get_virtual_group_members(route, context)
    local gmembers = ""
    db = assert(con:execute(string.format("SELECT * "..
            "FROM pbx_group_members INNER JOIN pbx_groups ON pbx_groups.id = pbx_group_members.pbx_group_id "..
            "WHERE pbx_groups.name='%s' "..
            "AND context='%s'", route["name"], context)))
    local group_members = db:fetch ({}, "a")
    while group_members do
        for ext, gateway in rows(string.format("SELECT did, default_gateway AS gateway "..
                "FROM pbx_virtual_extensions " ..
                "INNER JOIN customers ON customers.context=pbx_virtual_extensions.context " ..
                "WHERE extension= '%s' AND pbx_virtual_extensions.context = '%s'", group_members.extension, context)) do
            gmembers = gmembers .. ",[leg_delay_start=10,leg_timeout=15]sofia/gateway/" .. gateway .. "/" .. ext
        end
        group_members = db:fetch (group_members, "a")
    end
    return gmembers
end

function get_sequential_group_members(route, context)
    db = assert(con:execute(string.format("SELECT * FROM pbx_group_members "..
            "INNER JOIN pbx_groups "..
            "ON pbx_groups.id = pbx_group_members.pbx_group_id "..
            "WHERE pbx_groups.name='%s' AND context='%s'", route["name"], context)))
    return db:fetch ({}, "a")
end

function do_tod(name, context)
    db = assert(con:execute(string.format("SELECT * FROM "..
            "pbx_tod_routes WHERE context= '%s' AND name ='%s'", context, name)))
    local tod = db:fetch({}, "a")

    local day = os.date("%w")
    local hour = os.date("%H")
    local minutes = os.date("%M")

    local shour = string.sub(tod["time_start"], 2, 3)
    local sminutes = string.sub(tod["time_start"], 5, 6)

    local ehour = string.sub(tod['time_end'], 2, 3)
    local eminutes = string.sub(tod["time_end"], 5, 6)

    if tonumber(tod["day_start"]) <= tonumber(day) and tonumber(tod["day_end"]) >= tonumber(day) then
        if tonumber(hour..minutes) >= tonumber(shour..sminutes) and
                tonumber(hour..minutes) <= tonumber(ehour..eminutes) then
            return send_route(get_route_by_id(tod["match_route_id"]), context)
        else
            return send_route(get_route_by_id(tod["nomatch_route_id"]), context)
        end
    else
        return send_route(get_route_by_id(tod["nomatch_route_id"]), context)
    end
end

--[[ IVR Logic. ]]--
function do_ivr(route, context)
    session:answer()
    local ivr = get_ivr(route, context)

    while (session:ready() == true) do
        log(string.format("Caller has called PBX for %s\n", context))
        session:setAutoHangup(true)
        session:sleep(2000)

        digits = ""

        if ivr["audio_type"] == "1" then
            local path = "/usr/local/freeswitch/htdocs/vm/" .. context .. "/recordings/" .. ivr["data"]
            digits = session:playAndGetDigits(1, 4, 3, tonumber(ivr["timeout"].."000"), '', path,
                'voicemail/vm-that_was_an_invalid_ext.wav', '\\d+')
        elseif ivr["audio_type"] == "2" then
            session:setInputCallback("key_press", "")
            local tts = get_tts(ivr, context)
            session:sleep(1000)
            session:speak(tts["text"])
            session:sleep(tonumber(ivr["timeout"] .. "000"))
        end

        if string.len(digits) > 1 then
            if digits == "411" then
                session:transfer("411", "XML", context)
            end

            local keyed_route = get_route_by_ext(digits, context)
            if keyed_route == nil or ivr["direct_dial"] ~= "t" then
                session:execute("playback", "voicemail/vm-that_was_an_invalid_ext.wav")
            else
                send_route(keyed_route, context)
            end
        elseif string.len(digits) == 1 then
            local opt_route = get_route_by_ivr_opt(digits, ivr['id'])

            if opt_route == nil then
                session:execute("playback", "voicemail/vm-that_was_an_invalid_ext.wav")
            else
                send_route(opt_route, context)
            end
        else
            send_route(get_route_by_id(ivr["timeout_destination"]), context)
        end
    end
end

--[[ Some like the hold music for ringback and the hold while I try that extension. ]]--
function check_exists_available(extension, context)
    session:execute("set", "contact_exists=${user_exists(id " .. extension .. " ${domain})}")
    if(session:getVariable("contact_exists")=="false") then
        session:execute("playback", "voicemail/vm-that_was_an_invalid_ext.wav")
    else
        session:execute("set", "contact_available=${sofia_contact(".. profile .. "/" .. extension .. "@${domain})}")
        contact_available = session:getVariable("contact_available")
        if(string.find(contact_available, "error")) then
            session:speak("I am sorry, that person is unavailable.")
            session:execute("voicemail", profile .. " ".. context .. " " .. extension)
        else
            --session:sleep(2000)
            --session:execute("playback", "ivr/ivr-hold_connect_call.wav")
            --session:execute("set", "transfer_ringback=${hold_music}")
            bridge_local(get_route_by_ext(extension, context), context)
        end
    end
end

--[[ Checks pattern entries and matches them to databases. If they all fail, will go to default route for customer. ]]--
function outroute(cust_id)
    db = assert(con:execute(string.format("SELECT o.pattern as pattern, gw.name as gateway "..
            "FROM pbx_outbound_routes o "..
            "INNER JOIN pbx_gateways gw ON o.gateway_id=gw.id "..
            "WHERE customer_id='%s' ORDER BY o.id", cust_id)))
    local outs = db:fetch ({}, "a")
    while outs do
        for k,v in pairs(split(outs.pattern, "|")) do
            if string.match(string.sub(called_num,0, string.len(v)), v)==v then
                gateway = outs.gateway
                log("Match: " .. v)
                return true
            end
        end
        outs = db:fetch (outs, "a")
    end
    log("NO MATCH FOR OUTBOUND GATEWAY")
    return false
end

function bridge_local(route, context)
    local ext = get_extension(route['name'], context)
    if (ext["find_me"]=="t") then
        transfer_local(route, context)
    end

    if ext["record_inbound_calls"] == "t" then
        session:execute("record_session", "${base_dir}/htdocs/vm/" .. context ..
                "/extension-recordings/${caller_id_number}_${uuid}_inbound_${strftime(%Y-%m-%d-%H-%M-%S)}.mp3")
    end

    session:execute("set","user_id=" .. ext["user_id"])
    session:execute("set","customer_id=" .. ext["customer_id"])
    session:execute("set","call_timeout=" .. ext["call_timeout"])
    session:execute("set","continue_on_fail=true")
    session:execute("set","hangup_after_bridge=true")
    session:execute("set","ringback=%(2000,4000,440.0,480.0)")
    session:execute("bridge","user/" .. route['name'] .. "@" .. context)

    if ext["timeout_destination"] == nil then
        session:answer()
        session:sleep(1000)
        session:execute("voicemail", profile .." " .. context .. " " .. route['name'])
    else
        send_route(get_route_by_id(ext["timeout_destination"]), context)
    end
end

function bridge_external(route, context)
    local gw = get_default_gateway(context)

    session:execute("set","call_timeout=" .. route["timeout"])
    session:execute("set","continue_on_fail=true")
    session:execute("set","hangup_after_bridge=true")
    session:execute("set","effective_caller_id_name=" .. caller_name)
    session:execute("set","effective_caller_id_number=" .. caller_num)
    session:execute("set","ringback=%(2000,4000,440.0,480.0)")
    session:execute("bridge","sofia/gateway/" .. gw["default_gateway"] .. "/" .. route["did"])
    send_route(get_route_by_id(route["timeout_destination"]), context)
    session:hangup()
end

function bridge_outbound(name, num, to, cust_id)
    if outroute(cust_id)==false then
        local gw = get_default_gateway(context)
        gateway = gw["default_gateway"]
    end
    local ext = get_extension(user_name, context)
    if ext["record_outbound_calls"] == "t" then
        session:execute("record_session", "${base_dir}/htdocs/vm/" .. context ..
                "/extension-recordings/${caller_id_number}_${uuid}_outbound_${strftime(%Y-%m-%d-%H-%M-%S)}.mp3")
    end
    session:execute("set","continue_on_fail=false")
    session:execute("set","hangup_after_bridge=true")
    session:execute("set","ringback=%(2000,4000,440.0,480.0)")
    session:execute("set","effective_caller_id_name=" .. name)
    session:execute("set","effective_caller_id_number=" .. num)
    session:execute("bridge","sofia/gateway/" .. gateway .."/" .. to)
    session:hangup()
end

function bridge_group(route, context)
    local virtual_members = get_virtual_group_members(route, context) or ""
    local group = get_group(route["name"], context)

    session:sleep(1000)
    session:setVariable("effective_caller_id_name", "PBX " .. route["name"])
    session:execute("set","call_timeout=" .. group["timeout"])

    if group["ring_strategy"] == "seq" then
        session:execute("set","ignore_early_media=true")
        session:execute("set","continue_on_fail=true")
        session:execute("set","hangup_after_bridge=true")
        session:execute("set","ringback=%(2000,4000,440.0,480.0)")
        db = assert(con:execute(string.format("SELECT * "..
                "FROM pbx_group_members INNER JOIN pbx_groups "..
                "ON pbx_groups.id = pbx_group_members.pbx_group_id "..
                "WHERE pbx_groups.name='%s' AND context='%s' "..
                "ORDER BY pbx_group_members.id", route["name"], context)))
        local row = db:fetch ({}, "a")

        while row do
            session:execute("set","call_timeout=13")
            session:execute("bridge","user/" .. row.extension .. "@" .. context)
            row = db:fetch (row, "a")
        end

        db = assert(con:execute(string.format("SELECT * "..
                "FROM pbx_group_members "..
                "INNER JOIN pbx_groups "..
                "ON pbx_groups.id = pbx_group_members.pbx_group_id "..
                "WHERE pbx_groups.name='%s' "..
                "AND context='%s'", route["name"], context)))
        local row = db:fetch ({}, "a")

        while row do
            for ext, gateway in rows(string.format("SELECT did, default_gateway AS gateway "..
                    "FROM pbx_virtual_extensions "..
                    "INNER JOIN customers ON customers.context=pbx_virtual_extensions.context "..
                    "WHERE extension= '%s' AND pbx_virtual_extensions.context = '%s'", row.extension, context)) do
                session:execute("set","call_timeout=13")
                session:execute("bridge","sofia/gateway/".. gateway .."/"..ext)
            end
            row = db:fetch (row, "a")
        end
        session:execute("bridge", virtual_members)
        send_route(get_route_by_id(group["no_answer_destination"]), context)
    else
        session:execute("set","call_timeout="..group["timeout"])
        session:execute("set","continue_on_fail=true")
        session:execute("set","hangup_after_bridge=true")
        session:execute("set", "ringback=%(2000,4000,440.0,480.0)")
        session:execute("bridge","group/" .. route["name"] .. "@" .. context .. virtual_members)
        send_route(get_route_by_id(group["no_answer_destination"]), context)
    end
    session:hangup()
end

--[[ Buggy and unexpected behavior... ]]--
function transfer_local(route, context)
    session:setAutoHangup(false)
    session:sleep(1000)
    session:execute("transfer", route['name'] .. " XML" .. " " .. context)
end

function send_route(route, context)
    log(route["name"])
    if route["pbx_route_type_id"] == "1" then
        check_exists_available(route["name"], context)
    elseif route["pbx_route_type_id"] == "2" then
        bridge_external(get_virtual_extension(route, context), context)
    elseif route["pbx_route_type_id"] == "3" then
        do_virtual_mailbox(route, context)
    elseif route["pbx_route_type_id"] == "4" then
        bridge_group(route, context)
    elseif route["pbx_route_type_id"] == "5" then
        do_ivr(route, context)
    elseif route["pbx_route_type_id"] == "6" then
        do_tod(route["name"], context)
    elseif route["pbx_route_type_id"] == "7" then
        session:execute("set", "called_num=" .. route["name"])
        session:transfer(route["name"], "XML", context)
    elseif route["pbx_route_type_id"] == "10" then
        do_cc(route["name"], context)
    elseif route["pbx_route_type_id"] == "11" then
        session:transfer(route["name"], "XML", context)
    elseif route["pbx_route_type_id"] == "12" then
        session:transfer(route["name"], "XML", context)
    else
        log("No route type ID associated with call.")
    end
end

--[[
    -- Global Chunk --
 ]]

-- get session
context     = session:getVariable("context")
domain     = session:getVariable("domain")
is_outbound = session:getVariable("is_outbound")
is_inbound  = session:getVariable("is_inbound")
user_name   = session:getVariable("user_name")
is_authed   = session:getVariable("sip_authorized")
called_num  = session:getVariable("destination_number")
caller_num  = session:getVariable("caller_id_number")
caller_name = session:getVariable("caller_id_name")
profile     = session:getVariable("profile")

-- set session
session:setHangupHook("session_hangup_hook")
session:execute("set", "domain=" .. context)
session:execute("set", "domain_name=" .. context)
session:execute("set", "user_context=" .. context)
session:execute("set", "force_transfer_context=" .. context)
session:execute("set", "force_transfer_dialplan=XML")

log(called_num)

if string.len(called_num) > 10 then
    called_num = string.sub(called_num, string.len(called_num)-9, string.len(called_num))
end

--[[ Process Inbound/Outbound ]]--

-- IN
if is_inbound then
    session:execute("set", "call_direction=inbound")

    log("inbound in LUA")

    customer = get_customer_by_did(called_num)

    log("Customer ID: " .. customer['id'])
    local context_channels = get_outbound_channel_count_by_context(customer['context'])
    log("context count:" .. context_channels['channel_count'])

    db = assert(con:execute(string.format("SELECT did FROM pbx_dids d INNER JOIN customers c " ..
            "ON c.id = d.customer_id WHERE customer_id = %d" , customer['customer_id'])))
    local dids = db:fetch ({}, "a")

    local channels = tonumber(context_channels['channel_count'])

    while dids do
        log("Did: " .. dids['did'])
        channel_count = get_channel_count_by_did(dids['did'])
        channels = channels + tonumber(channel_count['channel_count'])
        dids = db:fetch (dids, "a")
    end

    log("Channels count: " .. tonumber(customer['inbound_channel_limit']))
    log("Channels:" .. channels)

    if channels > tonumber(customer['hard_channel_limit']) then
        session:execute("playback", "tone_stream://%(500,500,480,620)")
        session:hangup()
    end

    if string.len(caller_num)> 10 then
        caller_num = string.sub(caller_num, string.len(caller_num)-9, string.len(caller_num))
    end

    if blacklisted(caller_num, context) then
        session:hangup()
    end

    get_cid_route(caller_num, context)
    send_route(get_route_by_did(called_num), context)
end

-- OUT
if is_outbound and is_authed then

    session:execute("set", "call_direction=outbound")
    session:execute("set", "extension=" .. user_name)

    local cust = get_outbound_caller_id(user_name, context)
    session:execute("export", "customer_id=" .. cust["customer_id"])
    session:execute("export", "user_id=" .. cust["user_id"])

    db = assert(con:execute(string.format("SELECT did FROM pbx_dids d INNER JOIN customers c " ..
            "ON c.id = d.customer_id WHERE customer_id = %d" , cust['customer_id'])))
    local dids = db:fetch ({}, "a")

    local out_channels = get_outbound_channel_count_by_context(context)
    local channels = tonumber(out_channels['channel_count'])
    customer = get_customer_by_id(cust['customer_id'])

    while dids do
        log("Did: " .. dids['did'])
        channel_count = get_channel_count_by_did(dids['did'])
        channels = channels + tonumber(channel_count['channel_count'])
        dids = db:fetch (dids, "a")
    end

    log("Context: "..context)
    log("Domain: "..domain)
    log("Channels: " ..channels)
    log("Customer limit" ..customer['hard_channel_limit'])

    if channels >= tonumber(customer['hard_channel_limit']) then
        log("Limit reached...")
        session:execute("playback", "/usr/local/freeswitch/recordings/channel_audio/"..customer['channel_audio'])
        session:hangup()
    else
        log("Channels available...")
        log(tonumber(customer['hard_channel_limit']))
    end

    if string.len(cust["ext_number"]) > 6 then
        bridge_outbound(cust["ext_name"], cust["ext_number"], called_num, cust["customer_id"])
    else
        bridge_outbound(cust["customer_name"], cust["tel"], called_num, cust["customer_id"])
    end
end
