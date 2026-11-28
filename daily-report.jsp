<%@ page language="java" contentType="text/plain; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ page import="java.sql.*, java.util.*" %>
<%
    response.setContentType("text/plain; charset=UTF-8");
    response.setCharacterEncoding("UTF-8");
    response.setHeader("Access-Control-Allow-Origin", "*");

    java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd");
    String todayStr = sdf.format(new java.util.Date());

    String startDateStr = request.getParameter("start_date");
    if (startDateStr == null || !startDateStr.matches("^\\d{4}-\\d{2}-\\d{2}$")) {
        startDateStr = request.getParameter("date");
    }
    if (startDateStr == null || !startDateStr.matches("^\\d{4}-\\d{2}-\\d{2}$")) {
        startDateStr = todayStr;
    }

    String endDateStr = request.getParameter("end_date");
    if (endDateStr == null || !endDateStr.matches("^\\d{4}-\\d{2}-\\d{2}$")) {
        endDateStr = startDateStr;
    }
    if (startDateStr.compareTo(endDateStr) > 0) {
        String tmp = startDateStr;
        startDateStr = endDateStr;
        endDateStr = tmp;
    }

    Connection conn = null;
    try {
        Class.forName("oracle.jdbc.driver.OracleDriver");
        conn = DriverManager.getConnection("jdbc:oracle:thin:@127.0.0.1:1521:orcl", "db", "db");

        String modeParam = request.getParameter("mode");
        if ("latest_plates".equalsIgnoreCase(modeParam)) {
            out.println("[SECTION:LATEST_PLATES]");
            String sqlPlates =
                "SELECT SDEVICE, CLICENSEPLATE, TO_CHAR(TACTIONTIME, 'YYYY-MM-DD HH24:MI:SS'), SCARDTYPE " +
                "FROM ( " +
                "  SELECT SDEVICE, CLICENSEPLATE, TACTIONTIME, SCARDTYPE, " +
                "         ROW_NUMBER() OVER (PARTITION BY SDEVICE ORDER BY TACTIONTIME DESC) AS RN " +
                "  FROM UDBIDENTDATA " +
                "  WHERE TACTIONTIME >= SYSDATE - 14 AND CLICENSEPLATE IS NOT NULL AND CLICENSEPLATE > '0' AND CLICENSEPLATE NOT LIKE '%null%' " +
                ") WHERE RN = 1 AND SDEVICE > 0 ORDER BY SDEVICE";
            try (Statement stP = conn.createStatement();
                 ResultSet rsP = stP.executeQuery(sqlPlates)) {
                while (rsP.next()) {
                    String lp = rsP.getString(2);
                    if (lp != null) {
                        lp = lp.replaceAll("[^0-9A-Za-z]", "").trim();
                        if (lp.length() >= 5) {
                            out.println(rsP.getInt(1) + "\t" + lp + "\t" + rsP.getString(3) + "\t" + rsP.getInt(4));
                        }
                    }
                }
            }
            out.println("[SECTION:END]");
            return;
        }

        // 1. Daily / Range Breakdown from UDBMOVEMENT across ALL facilities (FlexRep Stat802 / Stat803)
        out.println("[SECTION:BREAKDOWN]");
        String sql1 =
            "SELECT SARTCLASSREF, STRANSTYPE, CTEXT, NVL(SUM(LTOTALQUANTITY), 0) AS QTY, COUNT(*) AS CNT, NVL(SUM(LAMOUNT), 0)/100.0 AS ILS " +
            "FROM UDBMOVEMENT " +
            "WHERE TACTIONTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY SARTCLASSREF, STRANSTYPE, CTEXT " +
            "ORDER BY SARTCLASSREF, STRANSTYPE";
        try (PreparedStatement ps1 = conn.prepareStatement(sql1)) {
            ps1.setString(1, startDateStr);
            ps1.setString(2, endDateStr);
            try (ResultSet rs1 = ps1.executeQuery()) {
                while (rs1.next()) {
                    String ct = rs1.getString(3);
                    if (ct == null) ct = "";
                    ct = ct.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').trim();
                    out.println(rs1.getInt(1) + "\t" + rs1.getInt(2) + "\t" + ct + "\t" + rs1.getLong(4) + "\t" + rs1.getLong(5) + "\t" + rs1.getDouble(6));
                }
            }
        }

        // 1B. Per-Facility Traffic & Revenue Breakdown from UDBMOVEMENT
        out.println("[SECTION:FACILITIES_TRAFFIC]");
        String sqlFac =
            "SELECT NVL(SFACILITY, 0) AS FAC_ID, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENT_TOT, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 AND STRANSTYPE = 1 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENT_TRANS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 AND STRANSTYPE = 2 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENT_SUB, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 AND STRANSTYPE = 4 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENT_APP, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXT_TOT, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 AND STRANSTYPE = 11 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXT_TRANS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 AND STRANSTYPE = 12 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXT_SUB, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 AND STRANSTYPE = 14 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXT_APP, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 1000 THEN LAMOUNT ELSE 0 END), 0)/100.0 AS REV_ILS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 17 AND STRANSTYPE IN (88,90,51,63) THEN LTOTALQUANTITY ELSE 0 END), 0) AS BAR_OPENS " +
            "FROM UDBMOVEMENT " +
            "WHERE TACTIONTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY NVL(SFACILITY, 0) " +
            "ORDER BY FAC_ID";
        try (PreparedStatement psF = conn.prepareStatement(sqlFac)) {
            psF.setString(1, startDateStr);
            psF.setString(2, endDateStr);
            try (ResultSet rsF = psF.executeQuery()) {
                while (rsF.next()) {
                    out.println(
                        rsF.getInt(1) + "\t" +
                        rsF.getLong(2) + "\t" +
                        rsF.getLong(3) + "\t" +
                        rsF.getLong(4) + "\t" +
                        rsF.getLong(5) + "\t" +
                        rsF.getLong(6) + "\t" +
                        rsF.getLong(7) + "\t" +
                        rsF.getLong(8) + "\t" +
                        rsF.getLong(9) + "\t" +
                        rsF.getDouble(10) + "\t" +
                        rsF.getLong(11)
                    );
                }
            }
        } catch (Exception ignore) {}

        // 1C. Live Pango (SDEVICE=610) & Cellopark (SDEVICE=699) from LOGGVORGANG
        out.println("[SECTION:PANGO_CELLO]");
        String sqlPC =
            "SELECT SDEVICE, COUNT(DISTINCT cepan) AS CNT, NVL(SUM(LTOTALAMOUNT), 0)/100.0 AS ILS " +
            "FROM loggvorgang " +
            "WHERE SDEVICE IN (610, 699) " +
            "  AND XTARIFFTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND XTARIFFTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY SDEVICE ORDER BY SDEVICE";
        try (PreparedStatement psPC = conn.prepareStatement(sqlPC)) {
            psPC.setString(1, startDateStr);
            psPC.setString(2, endDateStr);
            try (ResultSet rsPC = psPC.executeQuery()) {
                while (rsPC.next()) {
                    out.println(rsPC.getInt(1) + "\t" + rsPC.getLong(2) + "\t" + rsPC.getDouble(3));
                }
            }
        } catch (Exception ignore) {}

        // 1D. FlexRep Stat800 Occupancy Peak per Facility directly from DIFFCNTRHISTORY
        out.println("[SECTION:OCCUPANCY_PEAK]");
        String sqlOcc =
            "SELECT SFTYKEY, " +
            "       NVL(MAX(LKPPRESMAX), 0) AS PEAK_TRANS, " +
            "       NVL(MAX(LDPPRESMAX), 0) AS PEAK_SUB, " +
            "       NVL(MAX(LKPPRESMAX + LDPPRESMAX), 0) AS PEAK_TOT, " +
            "       NVL(MAX(LKPMAX), 0) AS MAX_KP, " +
            "       NVL(MAX(LDPMAX), 0) AS MAX_DP " +
            "FROM DIFFCNTRHISTORY " +
            "WHERE XDATE >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND XDATE <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY SFTYKEY " +
            "ORDER BY SFTYKEY";
        try (PreparedStatement psOcc = conn.prepareStatement(sqlOcc)) {
            psOcc.setString(1, startDateStr);
            psOcc.setString(2, endDateStr);
            try (ResultSet rsOcc = psOcc.executeQuery()) {
                while (rsOcc.next()) {
                    out.println(
                        rsOcc.getInt(1) + "\t" +
                        rsOcc.getLong(2) + "\t" +
                        rsOcc.getLong(3) + "\t" +
                        rsOcc.getLong(4) + "\t" +
                        rsOcc.getLong(5) + "\t" +
                        rsOcc.getLong(6)
                    );
                }
            }
        } catch (Exception ignore) {}

        // 1E. FlexRep Stat801 Stay Duration Breakdown directly from UDBMOVEMENT
        out.println("[SECTION:STAY_DURATION]");
        String sqlStay =
            "SELECT " +
            "  NVL(SUM(CASE WHEN STAY_MINS <= 15 THEN 1 ELSE 0 END), 0) AS S015, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 15 AND STAY_MINS <= 30 THEN 1 ELSE 0 END), 0) AS S030, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 30 AND STAY_MINS <= 45 THEN 1 ELSE 0 END), 0) AS S045, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 45 AND STAY_MINS <= 60 THEN 1 ELSE 0 END), 0) AS S060, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 60 AND STAY_MINS <= 120 THEN 1 ELSE 0 END), 0) AS S2, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 120 AND STAY_MINS <= 180 THEN 1 ELSE 0 END), 0) AS S3, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 180 AND STAY_MINS <= 240 THEN 1 ELSE 0 END), 0) AS S4, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 240 AND STAY_MINS <= 300 THEN 1 ELSE 0 END), 0) AS S5, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 300 AND STAY_MINS <= 360 THEN 1 ELSE 0 END), 0) AS S6, " +
            "  NVL(SUM(CASE WHEN STAY_MINS > 360 THEN 1 ELSE 0 END), 0) AS S724 " +
            "FROM ( " +
            "  SELECT e.CEPAN, (x.TACTIONTIME - MAX(e.TACTIONTIME)) * 1440.0 AS STAY_MINS " +
            "  FROM UDBMOVEMENT x " +
            "  JOIN UDBMOVEMENT e ON e.CEPAN = x.CEPAN " +
            "    AND e.SARTCLASSREF = 10 " +
            "    AND e.TACTIONTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') - 2 " +
            "    AND e.TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "    AND e.TACTIONTIME <= x.TACTIONTIME AND e.TACTIONTIME >= x.TACTIONTIME - 2 " +
            "  WHERE x.SARTCLASSREF = 11 " +
            "    AND x.TACTIONTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "    AND x.TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "    AND x.CEPAN IS NOT NULL AND x.CEPAN NOT LIKE '00000000%' " +
            "  GROUP BY e.CEPAN, x.LGLOBALID, x.TACTIONTIME " +
            ")";
        try (PreparedStatement psStay = conn.prepareStatement(sqlStay)) {
            psStay.setString(1, startDateStr);
            psStay.setString(2, endDateStr);
            psStay.setString(3, startDateStr);
            psStay.setString(4, endDateStr);
            try (ResultSet rsStay = psStay.executeQuery()) {
                if (rsStay.next()) {
                    out.println(
                        rsStay.getLong(1) + "\t" +
                        rsStay.getLong(2) + "\t" +
                        rsStay.getLong(3) + "\t" +
                        rsStay.getLong(4) + "\t" +
                        rsStay.getLong(5) + "\t" +
                        rsStay.getLong(6) + "\t" +
                        rsStay.getLong(7) + "\t" +
                        rsStay.getLong(8) + "\t" +
                        rsStay.getLong(9) + "\t" +
                        rsStay.getLong(10)
                    );
                }
            }
        } catch (Exception ignore) {}

        // 1F. TSETHELP Settled Daily Totals (if present on controller)
        out.println("[SECTION:TSETHELP]");
        String sqlTH =
            "SELECT SCOMPUTER, CTEXT, " +
            "       NVL(SUM(SCASH),0)/100.0 AS CASH_ILS, " +
            "       NVL(SUM(SCREDIT),0)/100.0 AS CRED_ILS, " +
            "       NVL(SUM(SPANGO),0)/100.0 AS PANGO_ILS, " +
            "       NVL(SUM(SCELO),0)/100.0 AS CELO_ILS, " +
            "       NVL(SUM(TOPENB),0) AS OPEN_B, " +
            "       NVL(SUM(TENTRYS),0) AS ENT_S, " +
            "       NVL(SUM(TENTRYP),0) AS ENT_P, " +
            "       NVL(SUM(TENTRYTOT),0) AS ENT_TOT, " +
            "       NVL(SUM(TEEITS),0) AS EXT_S, " +
            "       NVL(SUM(TEEITP),0) AS EXT_P, " +
            "       NVL(SUM(TEEITTOT),0) AS EXT_TOT " +
            "FROM TSETHELP " +
            "WHERE TRUNC(TTCRET) >= TO_DATE(?, 'YYYY-MM-DD') " +
            "  AND TRUNC(TTCRET) <= TO_DATE(?, 'YYYY-MM-DD') " +
            "GROUP BY SCOMPUTER, CTEXT " +
            "ORDER BY SCOMPUTER";
        try (PreparedStatement psTH = conn.prepareStatement(sqlTH)) {
            psTH.setString(1, startDateStr);
            psTH.setString(2, endDateStr);
            try (ResultSet rsTH = psTH.executeQuery()) {
                while (rsTH.next()) {
                    String ct = rsTH.getString(2);
                    if (ct == null) ct = "";
                    ct = ct.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').trim();
                    out.println(
                        rsTH.getLong(1) + "\t" +
                        ct + "\t" +
                        rsTH.getDouble(3) + "\t" +
                        rsTH.getDouble(4) + "\t" +
                        rsTH.getDouble(5) + "\t" +
                        rsTH.getDouble(6) + "\t" +
                        rsTH.getLong(7) + "\t" +
                        rsTH.getLong(8) + "\t" +
                        rsTH.getLong(9) + "\t" +
                        rsTH.getLong(10) + "\t" +
                        rsTH.getLong(11) + "\t" +
                        rsTH.getLong(12) + "\t" +
                        rsTH.getLong(13)
                    );
                }
            }
        } catch (Exception ignore) {}

        // 1G. USER_AUDIT Manual Barrier / Operator Actions Count
        out.println("[SECTION:USER_AUDIT_COUNT]");
        String sqlUA =
            "SELECT COUNT(*) FROM user_audit " +
            "WHERE TDATETIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND TDATETIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS')";
        try (PreparedStatement psUA = conn.prepareStatement(sqlUA)) {
            psUA.setString(1, startDateStr);
            psUA.setString(2, endDateStr);
            try (ResultSet rsUA = psUA.executeQuery()) {
                if (rsUA.next()) {
                    out.println(rsUA.getLong(1));
                }
            }
        } catch (Exception ignore) {}

        // 2. Hourly Traffic & Revenue
        out.println("[SECTION:HOURLY]");
        String sql2 =
            "SELECT TO_CHAR(TACTIONTIME, 'HH24') AS HR, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENTRIES, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXITS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 1000 THEN LAMOUNT ELSE 0 END), 0)/100.0 AS REV_ILS " +
            "FROM UDBMOVEMENT " +
            "WHERE TACTIONTIME >= TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') " +
            "  AND TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY TO_CHAR(TACTIONTIME, 'HH24') " +
            "ORDER BY HR";
        try (PreparedStatement ps2 = conn.prepareStatement(sql2)) {
            ps2.setString(1, startDateStr);
            ps2.setString(2, endDateStr);
            try (ResultSet rs2 = ps2.executeQuery()) {
                while (rs2.next()) {
                    out.println(rs2.getString(1) + "\t" + rs2.getLong(2) + "\t" + rs2.getLong(3) + "\t" + rs2.getDouble(4));
                }
            }
        }

        // 3. Recent / Range Days summary
        out.println("[SECTION:RECENT_DAYS]");
        String sql3 =
            "SELECT TO_CHAR(TACTIONTIME, 'YYYY-MM-DD') AS DT, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 10 THEN LTOTALQUANTITY ELSE 0 END), 0) AS ENTRIES, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 11 THEN LTOTALQUANTITY ELSE 0 END), 0) AS EXITS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 1000 THEN LAMOUNT ELSE 0 END), 0)/100.0 AS REV_ILS, " +
            "       NVL(SUM(CASE WHEN SARTCLASSREF = 1000 THEN LTOTALQUANTITY ELSE 0 END), 0) AS PAID_CNT " +
            "FROM UDBMOVEMENT " +
            "WHERE TACTIONTIME >= LEAST(TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS'), TO_DATE(? || ' 00:00:00', 'YYYY-MM-DD HH24:MI:SS') - 6) " +
            "  AND TACTIONTIME <= TO_DATE(? || ' 23:59:59', 'YYYY-MM-DD HH24:MI:SS') " +
            "GROUP BY TO_CHAR(TACTIONTIME, 'YYYY-MM-DD') " +
            "ORDER BY DT DESC";
        try (PreparedStatement ps3 = conn.prepareStatement(sql3)) {
            ps3.setString(1, startDateStr);
            ps3.setString(2, endDateStr);
            ps3.setString(3, endDateStr);
            try (ResultSet rs3 = ps3.executeQuery()) {
                while (rs3.next()) {
                    out.println(rs3.getString(1) + "\t" + rs3.getLong(2) + "\t" + rs3.getLong(3) + "\t" + rs3.getDouble(4) + "\t" + rs3.getLong(5));
                }
            }
        }

        // 4. FlexRep Report Catalog from FR_REPORT
        out.println("[SECTION:FLEXREP_REPORTS]");
        try (Statement st4 = conn.createStatement();
             ResultSet rs4 = st4.executeQuery("SELECT REPORT_ID, NAME, MEMO FROM FR_REPORT ORDER BY REPORT_ID")) {
            while (rs4.next()) {
                String rn = rs4.getString(2);
                String rm = rs4.getString(3);
                if (rn == null) rn = "";
                if (rm == null) rm = "";
                rn = rn.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').trim();
                rm = rm.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').trim();
                out.println(rs4.getInt(1) + "\t" + rn + "\t" + rm);
            }
        } catch (Exception ignore) {}

        out.println("[SECTION:END]");
    } catch (Exception e) {
        out.println("[ERROR] " + e.getMessage());
    } finally {
        try { if (conn != null) conn.close(); } catch (Exception ignore) {}
    }
%>
