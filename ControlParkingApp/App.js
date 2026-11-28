import React, { useState, useEffect, useRef } from 'react';
import {
  StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView,
  ActivityIndicator, Alert, StatusBar, RefreshControl,
  Modal, Image, AppState, Switch, useWindowDimensions,
  Keyboard, KeyboardAvoidingView, Platform, TouchableWithoutFeedback,
  InputAccessoryView
} from 'react-native';
import { SafeAreaView, SafeAreaProvider } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Clipboard from 'expo-clipboard';
import axios from 'axios';

const SERVER_URL = 'https://s-b-parking-reports.onrender.com';
const API_BASE_URL = `${SERVER_URL}/api/parking-control`;
const LOCAL_DEV_API_URL = __DEV__ ? 'http://172.20.10.2:5055/api/parking-control' : '';
const APP_VERSION = '1.0.1';
const COPYRIGHT_HOLDER = 'Hint LTD';
const KB_ACCESSORY_ID = 'sbControlKeyboardDoneBar';

export default function App() {
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;
  const isTablet = Math.min(width, height) >= 600;
  const isSplitLayout = isTablet || (isLandscape && width >= 700);

  // Sensitive Auth State (OTP required per operational session)
  const [authToken, setAuthToken] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const [parkingOptions, setParkingOptions] = useState([]);
  const [parkingChoiceModal, setParkingChoiceModal] = useState(false);

  // Login Screen State
  const [phoneInput, setPhoneInput] = useState('');
  const [initialCodeInput, setInitialCodeInput] = useState('');
  const [loginParkingChoices, setLoginParkingChoices] = useState([]);
  const [selectedProjectNumber, setSelectedProjectNumber] = useState('');
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [otpStep, setOtpStep] = useState(false);
  const [otpInput, setOtpInput] = useState('');
  const [directOtpCode, setDirectOtpCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  // Active Tab: 'ops' | 'counters' | 'companies' | 'search'
  const [activeTab, setActiveTab] = useState('ops');

  // Tab 1: Operations & Lanes
  const [lanes, setLanes] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [laneFilter, setLaneFilter] = useState('ALL');
  const [selectedUnitsMap, setSelectedUnitsMap] = useState({}); // { [unitId]: true } - empty means show all
  const [unitSelectorModal, setUnitSelectorModal] = useState(false);
  const [selectedUnit, setSelectedUnit] = useState(null);
  const [laneDetail, setLaneDetail] = useState(null);
  const [laneDetailLoading, setLaneDetailLoading] = useState(false);
  const [imageCacheBust, setImageCacheBust] = useState(Date.now());
  const [fixPlateText, setFixPlateText] = useState('');
  const [fixPlateFirstTapClear, setFixPlateFirstTapClear] = useState(false);
  const [fixIgnoreSim, setFixIgnoreSim] = useState(false);
  const [fixForceOpen, setFixForceOpen] = useState(false);
  const [exitPriceInput, setExitPriceInput] = useState('');
  const [screenPriceInfo, setScreenPriceInfo] = useState(null); // { active, price_ils, price_display, status_code }
  const [screenPriceLoading, setScreenPriceLoading] = useState(false);
  const [priceModalLane, setPriceModalLane] = useState(null); // lane object when opened from grid card
  const [actionBusy, setActionBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Tab 2: Online Counters & FlexRep Daily/Historical Reports
  const [countersData, setCountersData] = useState(null);
  const [countersLoading, setCountersLoading] = useState(false);
  const [counterEditModal, setCounterEditModal] = useState(null); // { facilityId, counterId, name, mode, value }
  const [counterEditValue, setCounterEditValue] = useState('');
  const [reportDateInput, setReportDateInput] = useState(new Date().toISOString().slice(0, 10));
  const [reportEndDateInput, setReportEndDateInput] = useState(new Date().toISOString().slice(0, 10));
  const [isDateRangeMode, setIsDateRangeMode] = useState(false);
  const [calendarModalTarget, setCalendarModalTarget] = useState(null); // null | 'start' | 'end'
  const [calendarViewYear, setCalendarViewYear] = useState(new Date().getFullYear());
  const [calendarViewMonth, setCalendarViewMonth] = useState(new Date().getMonth());
  const [dailyReportData, setDailyReportData] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Tab 3: Companies & Subscribers
  const [companies, setCompanies] = useState([]);
  const [companySearch, setCompanySearch] = useState('');
  const [companySearchFocused, setCompanySearchFocused] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [companyQuotaInput, setCompanyQuotaInput] = useState('');
  const [subscribers, setSubscribers] = useState([]);
  const [subSearch, setSubSearch] = useState('');
  const [subSearchFocused, setSubSearchFocused] = useState(false);
  const [subOnlyPresent, setSubOnlyPresent] = useState(false);
  const [companiesLoading, setCompaniesLoading] = useState(false);
  const [editingSub, setEditingSub] = useState(null);
  const [savingSubLoading, setSavingSubLoading] = useState(false);

  const companySearchInputRef = useRef(null);
  const subSearchInputRef = useRef(null);

  // Tab 4: Vehicle Search (Patrol + Transient Tariff)
  const [searchPlateInput, setSearchPlateInput] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState(null);

  const appState = useRef(AppState.currentState);
  const lastActivityRef = useRef(Date.now());
  const activeTokenRef = useRef('');
  const activeProjectRef = useRef('');
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes auto-logout for information security

  const markUserActivity = () => {
    lastActivityRef.current = Date.now();
  };

  // Load last used phone number & saved unit selection
  useEffect(() => {
    AsyncStorage.getItem('control_last_phone').then((savedPhone) => {
      if (savedPhone) setPhoneInput(savedPhone);
    });
    AsyncStorage.getItem('control_selected_units_map').then((savedJson) => {
      if (savedJson) {
        try {
          const parsed = JSON.parse(savedJson);
          if (parsed && typeof parsed === 'object') {
            setSelectedUnitsMap(parsed);
          }
        } catch (e) {}
      }
    });
  }, []);

  const toggleUnitInSelection = (unitId) => {
    const uKey = String(unitId);
    setSelectedUnitsMap((prev) => {
      const next = { ...prev };
      if (next[uKey]) {
        delete next[uKey];
      } else {
        next[uKey] = true;
      }
      AsyncStorage.setItem('control_selected_units_map', JSON.stringify(next)).catch(() => {});
      return next;
    });
  };

  const clearUnitSelectionFilter = () => {
    setSelectedUnitsMap({});
    AsyncStorage.removeItem('control_selected_units_map').catch(() => {});
  };

  const selectFacilityUnitsOnly = (facilityNum) => {
    const next = {};
    lanes.forEach((l) => {
      if (String(l.facility_number) === String(facilityNum)) {
        next[String(l.number || l.unit)] = true;
      }
    });
    setSelectedUnitsMap(next);
    AsyncStorage.setItem('control_selected_units_map', JSON.stringify(next)).catch(() => {});
  };

  // Auto-detect 6-digit OTP from Clipboard when returning from WhatsApp + enforce 30-min timeout
  useEffect(() => {
    const sub = AppState.addEventListener('change', async (nextState) => {
      if (nextState === 'active') {
        if (authToken && Date.now() - lastActivityRef.current >= SESSION_TIMEOUT_MS) {
          setAuthToken(null);
          setUserProfile(null);
          setSelectedUnit(null);
          setLaneDetail(null);
          Alert.alert('ניתוק אבטחה אוטומטי', 'נותקת מהמערכת לאחר 30 דקות לצורך אבטחת המידע. נא להתחבר מחדש.');
        } else if (otpStep) {
          try {
            const clip = await Clipboard.getStringAsync();
            if (clip) {
              const match = clip.match(/\b(\d{6})\b/);
              if (match && match[1]) {
                setOtpInput(match[1]);
                handleVerifyOtp(match[1]);
              }
            }
          } catch (e) {}
        }
      }
      appState.current = nextState;
    });
    return () => sub.remove();
  }, [otpStep, authToken]);

  // Periodic check for 30-minute session timeout while app is open
  useEffect(() => {
    if (!authToken) return;
    lastActivityRef.current = Date.now();
    const secTimer = setInterval(() => {
      if (Date.now() - lastActivityRef.current >= SESSION_TIMEOUT_MS) {
        setAuthToken(null);
        setUserProfile(null);
        setSelectedUnit(null);
        setLaneDetail(null);
        Alert.alert('ניתוק אבטחה אוטומטי', 'נותקת מהמערכת לאחר 30 דקות לצורך אבטחת המידע. נא להתחבר מחדש.');
      }
    }, 30000);
    return () => clearInterval(secTimer);
  }, [authToken]);

  const handlePasteOtpFromClipboard = async () => {
    try {
      const clip = await Clipboard.getStringAsync();
      if (clip) {
        const match = clip.match(/\b(\d{6})\b/) || [null, clip.replace(/\D/g, '').slice(0, 6)];
        const code6 = match[1] || '';
        if (code6.length === 6) {
          setOtpInput(code6);
          handleVerifyOtp(code6);
          return;
        }
      }
      Alert.alert('הדבקת קוד', 'לא נמצא קוד בן 6 ספרות בלוח ההעתקה (Clipboard). העתק את ההודעה מ-WhatsApp ונסה שוב.');
    } catch (e) {
      Alert.alert('שגיאה', 'לא ניתן לקרוא מלוח ההעתקה');
    }
  };

  // Periodic live refresh for Tab 1 via Render Server
  useEffect(() => {
    if (!authToken) return;
    loadOverview(true);
    const timer = setInterval(() => {
      if (activeTab === 'ops') {
        loadOverview(true);
      }
    }, 10000);
    return () => clearInterval(timer);
  }, [authToken, activeTab]);

  const apiHeaders = (overrideToken = null, overrideProject = null) => ({
    'Content-Type': 'application/json',
    'X-Control-Token': overrideToken || activeTokenRef.current || authToken || '',
    'X-Control-Project':
      overrideProject || activeProjectRef.current || userProfile?.project_number || selectedProjectNumber || ''
  });

  // =====================================================
  // AUTHENTICATION & MULTI-PARKING SELECTION (VIA RENDER)
  // =====================================================
  const handleSendOtp = async (chosenProject = '', chosenUid = null) => {
    Keyboard.dismiss();
    const cleanPhone = phoneInput.trim();
    const cleanCode = initialCodeInput.trim() || cleanPhone;
    if (!cleanPhone && !cleanCode) {
      Alert.alert('שגיאה', 'נא להזין מספר טלפון נייד או קוד זיהוי ראשוני');
      return;
    }
    setAuthLoading(true);
    try {
      const projToSend = chosenProject || selectedProjectNumber || '';
      const uidToSend = chosenUid || selectedUserId || null;
      const res = await axios.post(
        `${API_BASE_URL}/auth/send-otp`,
        {
          phone_number: cleanPhone,
          phone: cleanPhone,
          initial_code: cleanCode,
          project_number: projToSend,
          user_id: uidToSend
        },
        { timeout: 25000 }
      );
      const data = res.data;

      if (!data.success) {
        Alert.alert('שגיאת אימות', data.message || data.error || 'לא ניתן לשלוח קוד');
        setAuthLoading(false);
        return;
      }

      if (data.choose_parking && data.parkings && data.parkings.length > 1) {
        setLoginParkingChoices(data.parkings);
        setAuthLoading(false);
        return;
      }

      if (cleanPhone) {
        await AsyncStorage.setItem('control_last_phone', cleanPhone);
      }
      if (data.selected_project) {
        setSelectedProjectNumber(String(data.selected_project));
      }
      if (data.selected_user_id) {
        setSelectedUserId(data.selected_user_id);
      }
      if (data.parkings_options || data.parkings) {
        setParkingOptions(data.parkings_options || data.parkings || []);
      }
      setDirectOtpCode(data.otp_code || '');
      setOtpStep(true);
    } catch (err) {
      const serverMsg = err.response?.data?.message || err.response?.data?.error;
      Alert.alert(
        'שגיאת תקשורת',
        serverMsg || 'לא ניתן להתחבר לשרת Render. בדוק חיבור אינטרנט או המתן מספר שניות להערת השרת.'
      );
    } finally {
      setAuthLoading(false);
    }
  };

  const handleVerifyOtp = async (overrideCode = null) => {
    Keyboard.dismiss();
    const codeToVerify = String(overrideCode || otpInput || '').replace(/\D/g, '');
    if (codeToVerify.length !== 6) {
      Alert.alert('שגיאה', 'נא להזין את קוד האימות בן 6 הספרות');
      return;
    }
    setAuthLoading(true);
    try {
      const res = await axios.post(
        `${API_BASE_URL}/auth/verify-otp`,
        {
          phone_number: phoneInput.trim(),
          phone: phoneInput.trim(),
          initial_code: initialCodeInput.trim(),
          otp_code: codeToVerify,
          otp: codeToVerify,
          project_number: selectedProjectNumber,
          user_id: selectedUserId
        },
        { timeout: 25000 }
      );
      const data = res.data;
      const tk = data.auth_token || data.token;
      if (!data.success || !tk) {
        Alert.alert('אימות נכשל', data.message || data.error || 'קוד האימות שגוי');
        setAuthLoading(false);
        return;
      }
      activeTokenRef.current = tk;
      activeProjectRef.current = String(data.user?.project_number || selectedProjectNumber || '');
      setAuthToken(tk);
      setUserProfile(data.user);
      setParkingOptions(data.parkings_options || []);
      setOtpStep(false);
      setOtpInput('');
      setDirectOtpCode('');
    } catch (err) {
      Alert.alert(
        'אימות נכשל',
        err.response?.data?.message || err.response?.data?.error || 'קוד אימות שגוי או פג תוקף'
      );
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSwitchParking = async (projectNumber) => {
    setParkingChoiceModal(false);
    const targetProjStr = String(projectNumber || '').trim();
    if (!targetProjStr || targetProjStr === String(activeProjectRef.current || userProfile?.project_number)) return;
    try {
      const res = await axios.post(
        `${API_BASE_URL}/switch-parking`,
        { project_number: targetProjStr },
        { headers: apiHeaders(), timeout: 20000 }
      );
      if (res.data.success) {
        const newTk = res.data.auth_token || res.data.token || authToken;
        activeTokenRef.current = newTk;
        activeProjectRef.current = targetProjStr;
        setAuthToken(newTk);
        if (res.data.user) {
          setUserProfile(res.data.user);
        }
        if (res.data.parkings_options) {
          setParkingOptions(res.data.parkings_options);
        }
        setSelectedProjectNumber(targetProjStr);
        setSelectedUnitsMap({});
        setLanes([]);
        setSelectedUnit(null);
        setLaneDetail(null);
        setSelectedCompany(null);
        setCompanies([]);
        setSubscribers([]);
        setCountersData(null);
        setDailyReportData(null);
        setSearchResult(null);

        loadOverview(false, newTk, true, targetProjStr);
        if (activeTab === 'counters') loadCounters(newTk, null, null, targetProjStr);
        if (activeTab === 'companies') loadCompanies(newTk, targetProjStr);
      } else {
        Alert.alert('שגיאה', res.data.message || 'לא ניתן להחליף חניון');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'לא ניתן להחליף חניון');
    }
  };

  const handleLogout = () => {
    Alert.alert('יציאה ונעילת מסוף', 'האם לנעול את מסוף התפעול ולצאת? בכניסה הבאה יידרש קוד אימות חדש.', [
      { text: 'ביטול', style: 'cancel' },
      {
        text: 'נעל וצא',
        style: 'destructive',
        onPress: () => {
          activeTokenRef.current = '';
          activeProjectRef.current = '';
          setAuthToken(null);
          setUserProfile(null);
          setSelectedUnit(null);
          setLaneDetail(null);
          setLoginParkingChoices([]);
        }
      }
    ]);
  };

  // =====================================================
  // TAB 1: OPERATIONS & LANES (SORTED BY PARKING FACILITY: ENTRIES -> EXITS)
  // =====================================================
  const sortLanesByFacilityAndDirection = (list) => {
    const dirRank = (l) => {
      const d = String(l.direction || l.category || '').toLowerCase();
      if (d === 'entry') return 1;
      if (d === 'exit') return 2;
      if (d === 'passage') return 3;
      return 4;
    };
    return [...list].sort((a, b) => {
      const fA = parseInt(a.facility_number || '9999', 10) || 9999;
      const fB = parseInt(b.facility_number || '9999', 10) || 9999;
      if (fA !== fB) return fA - fB;
      const dA = dirRank(a);
      const dB = dirRank(b);
      if (dA !== dB) return dA - dB;
      const uA = parseInt(a.number || a.unit || '9999', 10) || 9999;
      const uB = parseInt(b.number || b.unit || '9999', 10) || 9999;
      return uA - uB;
    });
  };

  const loadOverview = async (silent = false, customToken = null, forceRefresh = false, customProject = null) => {
    if (!silent) setRefreshing(true);
    const forceQs = forceRefresh ? '?force=1' : '';
    const hdrs = apiHeaders(customToken, customProject);
    try {
      let ovData = null;

      // 1. In local dev (VPN connected), try local helper first for instant (<0.5s) load on both Mivne TLV & Shaare Zedek
      if (LOCAL_DEV_API_URL) {
        try {
          const localRes = await axios.get(`${LOCAL_DEV_API_URL}/overview${forceQs}`, {
            headers: hdrs,
            timeout: 5000
          });
          if (localRes.data?.success && Array.isArray(localRes.data.lanes) && localRes.data.lanes.length > 0) {
            ovData = localRes.data;
          }
        } catch (eLocal) {}
      }

      // 2. Fallback to Render server if local helper didn't return lanes
      if (!ovData) {
        const res = await axios.get(`${API_BASE_URL}/overview${forceQs}`, {
          headers: hdrs,
          timeout: 20000
        });
        if (res.data?.success) {
          ovData = res.data;
        }
      }

      if (ovData?.success) {
        const fetchedLanes = ovData.lanes || [];
        const sortedLanes = sortLanesByFacilityAndDirection(fetchedLanes);
        setLanes(sortedLanes);
        setAuditEvents(ovData.audit_events || ovData.recent_audits || []);
        if (ovData.user) {
          activeProjectRef.current = String(ovData.user.project_number || activeProjectRef.current || '');
          setUserProfile(ovData.user);
        }
        if (ovData.parkings_options && ovData.parkings_options.length > 0) {
          setParkingOptions(ovData.parkings_options);
        }
        if (!selectedUnit && sortedLanes.length > 0 && isSplitLayout) {
          const firstUnit = sortedLanes[0].number || sortedLanes[0].unit;
          selectLane(firstUnit, true);
        }
      }
    } catch (err) {
      if (err.response?.status === 401) {
        setAuthToken(null);
      } else if (!silent) {
        Alert.alert('שגיאה', err.response?.data?.message || 'שגיאה בטעינת נתוני נתיבים מהשרת');
      }
    } finally {
      if (!silent) setRefreshing(false);
    }
  };

  const checkExitScreenPrice = async (unitNum, cellNum = '1') => {
    const uStr = String(unitNum);
    const devNum = parseInt(uStr, 10) || 0;
    if (!(devNum >= 200 && devNum <= 299) && !(devNum >= 600 && devNum <= 699)) {
      setScreenPriceInfo(null);
      return null;
    }
    setScreenPriceLoading(true);
    try {
      let spData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.get(`${LOCAL_DEV_API_URL}/device-price/${uStr}?cell=${encodeURIComponent(cellNum)}`, {
            headers: apiHeaders(),
            timeout: 3500
          });
          if (rLoc.data?.success && rLoc.data.screen_price) {
            spData = rLoc.data.screen_price;
          }
        } catch (eL) {}
      }
      if (!spData) {
        const rRem = await axios.get(`${API_BASE_URL}/device-price/${uStr}?cell=${encodeURIComponent(cellNum)}`, {
          headers: apiHeaders(),
          timeout: 8000
        });
        if (rRem.data?.success && rRem.data.screen_price) {
          spData = rRem.data.screen_price;
        }
      }
      if (spData) {
        setScreenPriceInfo(spData);
        if (spData.active && spData.price_ils > 0) {
          setExitPriceInput(String(spData.price_ils));
        }
      }
      return spData;
    } catch (e) {
      return null;
    } finally {
      setScreenPriceLoading(false);
    }
  };

  const sendPriceToExitUnit = async (laneOrUnit, customAmountStr = null) => {
    const laneObj =
      typeof laneOrUnit === 'object' && laneOrUnit !== null
        ? laneOrUnit
        : lanes.find((l) => String(l.number || l.unit) === String(laneOrUnit)) || {
            number: String(laneOrUnit),
            cell_number: '1',
            name: `יציאה ${laneOrUnit}`
          };
    const unitNum = String(laneObj.number || laneObj.unit);
    const cellNum = String(laneObj.cell_number || '1');
    const rawAmount = (customAmountStr !== null ? customAmountStr : exitPriceInput || '').toString().trim();
    const amountVal = parseFloat(rawAmount);
    if (isNaN(amountVal) || amountVal <= 0) {
      Alert.alert('שגיאה', 'נא להזין סכום לתשלום בש"ח (למשל 25)');
      return;
    }
    Keyboard.dismiss();
    setActionBusy(true);
    try {
      const payload = {
        unit: unitNum,
        cell: cellNum,
        amount_ils: amountVal,
        plate: laneDetail?.plate || laneObj.last_plate || ''
      };
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/send-price`, payload, {
            headers: apiHeaders(),
            timeout: 16000
          });
          if (rLoc.data) resData = rLoc.data;
        } catch (eL) {}
      }
      if (!resData) {
        const rRem = await axios.post(`${API_BASE_URL}/send-price`, payload, {
          headers: apiHeaders(),
          timeout: 20000
        });
        resData = rRem.data;
      }
      if (resData?.screen_price) {
        setScreenPriceInfo(resData.screen_price);
      }
      if (resData?.success) {
        Alert.alert('מחיר נשלח לצג', resData.message || `המחיר ₪${amountVal} נשלח לצג יחידה ${unitNum}`);
        setPriceModalLane(null);
      } else {
        Alert.alert('שים לב', resData?.message || 'לא ניתן להציג מחיר על הצג כרגע');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'שגיאה בשליחת מחיר ליחידת היציאה');
    } finally {
      setActionBusy(false);
    }
  };

  const openExitPriceModalFromCard = async (lane) => {
    const unitNum = String(lane.number || lane.unit);
    const cellNum = String(lane.cell_number || '1');
    setPriceModalLane(lane);
    setExitPriceInput('');
    setScreenPriceInfo(null);
    await checkExitScreenPrice(unitNum, cellNum);
  };

  const selectLane = async (unit, silent = false) => {
    markUserActivity();
    const uStr = String(unit);
    const laneFromGrid = lanes.find((l) => String(l.number || l.unit) === uStr);
    const gridPlate = (laneFromGrid?.last_plate || laneFromGrid?.formatted_plate || '').replace(/[^0-9A-Za-zמ]/g, '');
    setSelectedUnit(uStr);
    if (gridPlate) {
      setFixPlateText(gridPlate);
      setFixPlateFirstTapClear(false);
    }
    if (!silent) setLaneDetailLoading(true);
    try {
      let detailData = null;
      // On-demand single-lane plate lookup from local helper in local dev
      if (LOCAL_DEV_API_URL) {
        try {
          const localDet = await axios.get(`${LOCAL_DEV_API_URL}/lane-detail/${uStr}`, {
            headers: apiHeaders(),
            timeout: 5000
          });
          if (localDet.data?.success && localDet.data.plate) {
            detailData = localDet.data;
          }
        } catch (eLoc) {}
      }

      if (!detailData) {
        const res = await axios.get(`${API_BASE_URL}/lane-detail/${uStr}`, {
          headers: apiHeaders(),
          timeout: 15000
        });
        if (res.data.success) {
          detailData = res.data;
        }
      }

      if (detailData) {
        const rawDetected = (detailData.plate || detailData.current_plate || gridPlate || '').replace(/[^0-9A-Za-zמ]/g, '');
        const bestFmt = detailData.formatted_plate || laneFromGrid?.formatted_plate || rawDetected;
        setLaneDetail({
          ...detailData,
          plate: rawDetected,
          formatted_plate: bestFmt
        });
        if (detailData.screen_price) {
          setScreenPriceInfo(detailData.screen_price);
          if (detailData.screen_price.active && detailData.screen_price.price_ils > 0) {
            setExitPriceInput(String(detailData.screen_price.price_ils));
          }
        } else {
          const devN = parseInt(uStr, 10) || 0;
          if (devN >= 200 && devN <= 299) {
            checkExitScreenPrice(uStr, laneFromGrid?.cell_number || '1');
          } else {
            setScreenPriceInfo(null);
          }
        }
        const calcDue = detailData.vehicle?.price_info?.amount_nis;
        if (calcDue && calcDue > 0) {
          setExitPriceInput(String(calcDue));
        }
        setFixPlateText(rawDetected);
        setFixPlateFirstTapClear(true);
        if (rawDetected) {
          setLanes((prevLanes) =>
            prevLanes.map((ln) =>
              String(ln.number || ln.unit) === uStr
                ? { ...ln, last_plate: rawDetected, formatted_plate: bestFmt }
                : ln
            )
          );
        }
      }
    } catch (err) {
      if (!silent) Alert.alert('שגיאה', 'לא ניתן לטעון פרטי נתיב מהשרת');
    } finally {
      if (!silent) setLaneDetailLoading(false);
    }
  };

  const sendLaneCommand = async (laneOrUnit, command, labelHe = '') => {
    const laneObj =
      typeof laneOrUnit === 'object' && laneOrUnit !== null
        ? laneOrUnit
        : lanes.find((l) => String(l.number || l.unit) === String(laneOrUnit)) || {
            number: String(laneOrUnit),
            cell_number: '1',
            name: `נתיב ${laneOrUnit}`
          };
    const unitNum = String(laneObj.number || laneObj.unit);
    const cellNum = String(laneObj.cell_number || '1');
    const unitName = laneObj.name || `נתיב ${unitNum}`;

    const isLockOrBlock = ['LOCK_BARRIER', 'BLOCK_DEVICE', 'OUT_OF_ORDER'].includes(command);
    const execute = async () => {
      setActionBusy(true);
      const payload = {
        unit: unitNum,
        cell: cellNum,
        unit_name: unitName,
        action: command,
        command: command
      };
      try {
        let resData = null;
        if (LOCAL_DEV_API_URL) {
          try {
            const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/command`, payload, {
              headers: apiHeaders(),
              timeout: 7000
            });
            if (rLoc.data?.success) resData = rLoc.data;
          } catch (eLoc) {}
        }
        if (!resData?.success) {
          try {
            const res = await axios.post(`${API_BASE_URL}/command`, payload, {
              headers: apiHeaders(),
              timeout: 12000
            });
            if (res.data) resData = res.data;
          } catch (eRem) {}
        }
        if (resData?.success) {
          Alert.alert('בוצע בהצלחה', resData.message || `${labelHe || command} בנתיב ${unitNum}`);
          loadOverview(true);
          if (String(selectedUnit) === unitNum) selectLane(unitNum, true);
        } else {
          Alert.alert('שגיאת פקודה', resData?.message || resData?.error || 'הפקודה נכשלה');
        }
      } catch (err) {
        Alert.alert('שגיאה', err.response?.data?.message || 'שגיאת תקשורת עם השרת');
      } finally {
        setActionBusy(false);
      }
    };

    if (isLockOrBlock) {
      Alert.alert('אישור פעולה רגישה', `האם לבצע "${labelHe || command}" ב-${unitName} (#${unitNum})?`, [
        { text: 'ביטול', style: 'cancel' },
        { text: 'בצע פעולה', style: 'destructive', onPress: execute }
      ]);
    } else {
      execute();
    }
  };

  const submitFixPlate = async () => {
    if (!selectedUnit) return;
    const clean = fixPlateText.replace(/[^A-Za-z0-9מ]/g, '').toUpperCase();
    if (clean.length < 5) {
      Alert.alert('שגיאה', 'נא להזין מספר רישוי תקין (לפחות 5 תווים)');
      return;
    }
    const laneObj = lanes.find((l) => String(l.number || l.unit) === String(selectedUnit)) || {
      cell_number: '1',
      facility_number: '1'
    };
    const payload = {
      unit: String(selectedUnit),
      cell: String(laneObj.cell_number || '1'),
      facility_number: String(laneObj.facility_number || '1'),
      camera_plate: laneDetail?.plate || laneDetail?.current_plate || '',
      entered_plate: clean,
      manager_override: fixIgnoreSim,
      force_open: fixForceOpen
    };
    setActionBusy(true);
    try {
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/fix-plate`, payload, {
            headers: apiHeaders(),
            timeout: 8000
          });
          if (rLoc.data?.success || rLoc.data?.action) resData = rLoc.data;
        } catch (eLoc) {}
      }
      if (!resData?.success) {
        try {
          const res = await axios.post(`${API_BASE_URL}/fix-plate`, payload, {
            headers: apiHeaders(),
            timeout: 15000
          });
          if (res.data) resData = res.data;
        } catch (eRem) {}
      }
      if (resData?.success) {
        Alert.alert('תיקון רכב בוצע', resData.message || 'הפעולה הושלמה ונרשמה באירועים');
        loadOverview(true);
        selectLane(selectedUnit, true);
      } else {
        Alert.alert('לידיעתך', resData?.message || resData?.error || 'לא בוצעה פתיחה אוטומטית');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'לא ניתן לבצע תיקון רכב');
    } finally {
      setActionBusy(false);
    }
  };

  // =====================================================
  // TAB 2: ONLINE COUNTERS & FLEXREP DAILY/HISTORICAL REPORTS
  // =====================================================
  const fetchDailyReportWithLocalFallback = async (startDt, endDt = null, customToken = null, customProject = null) => {
    const sDate = (startDt || reportDateInput || new Date().toISOString().slice(0, 10)).trim();
    const eDate = (endDt || (isDateRangeMode ? reportEndDateInput : sDate) || sDate).trim();
    const qs = `date=${encodeURIComponent(sDate)}&start_date=${encodeURIComponent(sDate)}&end_date=${encodeURIComponent(eDate)}`;
    const hdrs = apiHeaders(customToken, customProject);

    // Local PC server fallback first if running in local dev (connects to live Oracle DB on 1521 via VPN)
    if (LOCAL_DEV_API_URL) {
      try {
        const rLocal = await axios.get(`${LOCAL_DEV_API_URL}/daily-report?${qs}`, {
          headers: hdrs,
          timeout: 8000
        });
        if (rLocal.data?.success && rLocal.data?.daily_report && rLocal.data.daily_report.source !== 'none') {
          return rLocal.data.daily_report;
        }
      } catch (eLocal) {}
    }

    try {
      const r1 = await axios.get(`${API_BASE_URL}/daily-report?${qs}`, {
        headers: hdrs,
        timeout: 15000
      });
      if (r1.data?.success && r1.data?.daily_report && r1.data.daily_report.source !== 'none') {
        return r1.data.daily_report;
      }
    } catch (e) {}
    return null;
  };

  const loadCounters = async (customToken = null, customStartDate = null, customEndDate = null, customProject = null) => {
    markUserActivity();
    setCountersLoading(true);
    const sDate = customStartDate || reportDateInput || new Date().toISOString().slice(0, 10);
    const eDate = customEndDate || (isDateRangeMode ? reportEndDateInput : sDate) || sDate;
    const qs = `date=${encodeURIComponent(sDate)}&start_date=${encodeURIComponent(sDate)}&end_date=${encodeURIComponent(eDate)}`;
    const hdrs = apiHeaders(customToken, customProject);
    const hasRealCounters = (d) =>
      d?.success &&
      Array.isArray(d.facilities) &&
      d.facilities.some((f) => (f.counters?.length || 0) > 0 || (f.standard_counters?.length || 0) > 0);
    try {
      let cData = null;

      // 1. In local dev, try local helper first (connects to both Mivne TLV & Shaare Zedek + live Oracle DB in <1s)
      if (LOCAL_DEV_API_URL) {
        try {
          const localCnt = await axios.get(`${LOCAL_DEV_API_URL}/counters?${qs}`, {
            headers: hdrs,
            timeout: 8000
          });
          if (hasRealCounters(localCnt.data)) {
            cData = localCnt.data;
          }
        } catch (eLoc) {}
      }

      // 2. Fallback to Render server
      if (!cData) {
        try {
          const res = await axios.get(`${API_BASE_URL}/counters?${qs}`, {
            headers: hdrs,
            timeout: 20000
          });
          if (hasRealCounters(res.data) || res.data?.success) {
            cData = res.data;
          }
        } catch (eRem) {}
      }

      if (cData) {
        setCountersData(cData);
        if (cData.daily_report && cData.daily_report.source !== 'none') {
          setDailyReportData(cData.daily_report);
        } else {
          const fallbackRep = await fetchDailyReportWithLocalFallback(sDate, eDate, customToken, customProject);
          if (fallbackRep) {
            setDailyReportData(fallbackRep);
          } else if (cData.daily_report) {
            setDailyReportData(cData.daily_report);
          }
        }
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'לא ניתן לטעון מונים מבקר החניון');
    } finally {
      setCountersLoading(false);
    }
  };

  const loadDailyReportOnly = async (targetStartDate, targetEndDate = null) => {
    Keyboard.dismiss();
    const sDate = (targetStartDate || reportDateInput || '').trim();
    if (!sDate) return;
    const eDate = (targetEndDate || (isDateRangeMode ? reportEndDateInput : sDate) || sDate).trim();
    setReportDateInput(sDate);
    setReportEndDateInput(eDate);
    setReportLoading(true);
    try {
      const rep = await fetchDailyReportWithLocalFallback(sDate, eDate);
      if (rep) {
        setDailyReportData(rep);
      } else {
        await loadCounters(null, sDate, eDate);
      }
    } finally {
      setReportLoading(false);
    }
  };

  const shiftReportDate = (offsetDays) => {
    const dt = new Date();
    dt.setDate(dt.getDate() + offsetDays);
    const iso = dt.toISOString().slice(0, 10);
    setIsDateRangeMode(false);
    setReportDateInput(iso);
    setReportEndDateInput(iso);
    loadDailyReportOnly(iso, iso);
  };

  const selectLast7DaysRange = () => {
    const endDt = new Date();
    const startDt = new Date();
    startDt.setDate(endDt.getDate() - 6);
    const sIso = startDt.toISOString().slice(0, 10);
    const eIso = endDt.toISOString().slice(0, 10);
    setIsDateRangeMode(true);
    setReportDateInput(sIso);
    setReportEndDateInput(eIso);
    loadDailyReportOnly(sIso, eIso);
  };

  const openCalendarPicker = (targetField) => {
    const currentVal = targetField === 'end' ? reportEndDateInput : reportDateInput;
    const parts = (currentVal || '').split('-');
    if (parts.length === 3) {
      const y = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10) - 1;
      if (!isNaN(y) && !isNaN(m) && m >= 0 && m <= 11) {
        setCalendarViewYear(y);
        setCalendarViewMonth(m);
      }
    }
    setCalendarModalTarget(targetField);
  };

  const handleCalendarDayPick = (dayNum) => {
    const yStr = String(calendarViewYear);
    const mStr = String(calendarViewMonth + 1).padStart(2, '0');
    const dStr = String(dayNum).padStart(2, '0');
    const pickedIso = `${yStr}-${mStr}-${dStr}`;

    if (calendarModalTarget === 'end') {
      const sDate = reportDateInput > pickedIso ? pickedIso : reportDateInput;
      setReportDateInput(sDate);
      setReportEndDateInput(pickedIso);
      setCalendarModalTarget(null);
      loadDailyReportOnly(sDate, pickedIso);
    } else {
      setReportDateInput(pickedIso);
      const eDate = isDateRangeMode ? (reportEndDateInput < pickedIso ? pickedIso : reportEndDateInput) : pickedIso;
      setReportEndDateInput(eDate);
      setCalendarModalTarget(null);
      loadDailyReportOnly(pickedIso, eDate);
    }
  };

  const updateCounterAction = async (facilityId, counterId, operation, value) => {
    const payload = { facility_id: facilityId, counter_id: counterId, operation, value };
    try {
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/counters/update`, payload, {
            headers: apiHeaders(),
            timeout: 7000
          });
          if (rLoc.data?.success) resData = rLoc.data;
        } catch (eLoc) {}
      }
      if (!resData?.success) {
        try {
          const res = await axios.post(`${API_BASE_URL}/counters/update`, payload, {
            headers: apiHeaders(),
            timeout: 12000
          });
          if (res.data) resData = res.data;
        } catch (eRem) {}
      }
      if (resData?.success) {
        Alert.alert('עודכן', resData.message || 'המונה עודכן בהצלחה');
        setCounterEditModal(null);
        loadCounters();
      } else {
        Alert.alert('שגיאה', resData?.message || 'עדכון מונה נכשל');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'עדכון מונה נכשל');
    }
  };

  // =====================================================
  // TAB 3: COMPANIES & SUBSCRIBERS
  // =====================================================
  const loadCompanies = async (customToken = null, customProject = null) => {
    setCompaniesLoading(true);
    const hdrs = apiHeaders(customToken, customProject);
    try {
      let compData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.get(`${LOCAL_DEV_API_URL}/companies`, {
            headers: hdrs,
            timeout: 7000
          });
          if (rLoc.data?.success && Array.isArray(rLoc.data.companies) && rLoc.data.companies.length > 0) {
            compData = rLoc.data;
          }
        } catch (eL) {}
      }
      if (!compData) {
        const res = await axios.get(`${API_BASE_URL}/companies`, {
          headers: hdrs,
          timeout: 20000
        });
        if (res.data?.success) {
          compData = res.data;
        }
      }
      if (compData?.success) {
        setCompanies(compData.companies || []);
      } else {
        Alert.alert('שגיאה', compData?.message || 'לא ניתן לטעון חברות');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'לא ניתן לטעון רשימת חברות');
    } finally {
      setCompaniesLoading(false);
    }
  };

  const openCompanySubscribers = async (company) => {
    setSelectedCompany(company);
    setCompanyQuotaInput(String(company.max_counter ?? company.maxCounter ?? 0));
    setCompaniesLoading(true);
    const hdrs = apiHeaders();
    try {
      let subData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.get(`${LOCAL_DEV_API_URL}/companies/${company.id}/subscribers`, {
            headers: hdrs,
            timeout: 12000
          });
          if (rLoc.data?.success && Array.isArray(rLoc.data.subscribers)) {
            subData = rLoc.data;
          }
        } catch (eLoc) {}
      }
      if (!subData) {
        try {
          const res = await axios.get(`${API_BASE_URL}/companies/${company.id}/subscribers`, {
            headers: hdrs,
            timeout: 25000
          });
          if (res.data?.success) {
            subData = res.data;
          }
        } catch (eRem) {}
      }
      if (subData?.success) {
        if (subData.company) {
          setSelectedCompany(subData.company);
          setCompanyQuotaInput(String(subData.company.max_counter ?? 0));
        }
        setSubscribers(subData.subscribers || []);
      } else {
        Alert.alert('שגיאה', 'לא ניתן לטעון מנויים לחברה זו');
      }
    } catch (err) {
      Alert.alert('שגיאה', 'לא ניתן לטעון מנויים לחברה זו');
    } finally {
      setCompaniesLoading(false);
    }
  };

  const saveCompanyQuota = async () => {
    if (!selectedCompany) return;
    Keyboard.dismiss();
    const newMax = parseInt(companyQuotaInput || '0', 10);
    const payload = {
      contract_id: selectedCompany.id,
      max_counter: newMax
    };
    try {
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/company/update-quota`, payload, {
            headers: apiHeaders(),
            timeout: 8000
          });
          if (rLoc.data?.success) resData = rLoc.data;
        } catch (eLoc) {}
      }
      if (!resData?.success) {
        try {
          const res = await axios.post(`${API_BASE_URL}/company/update-quota`, payload, {
            headers: apiHeaders(),
            timeout: 12000
          });
          if (res.data) resData = res.data;
        } catch (eRem) {}
      }
      if (resData?.success) {
        Alert.alert('עודכן', resData.message || 'מכסת החברה עודכנה בהצלחה');
        setSelectedCompany({ ...selectedCompany, max_counter: newMax });
        setCompanies((prev) =>
          prev.map((c) => (String(c.id) === String(selectedCompany.id) ? { ...c, max_counter: newMax } : c))
        );
      } else {
        Alert.alert('שגיאה', resData?.message || 'עדכון מכסה נכשל');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'עדכון מכסה נכשל');
    }
  };

  const saveSubscriberEdit = async () => {
    if (!editingSub || !selectedCompany || savingSubLoading) return;
    Keyboard.dismiss();
    const newFirstName = (editingSub.first_name ?? editingSub.firstName ?? '').trim();
    const newLastName = (editingSub.last_name ?? editingSub.lastName ?? '').trim();
    const newLpn1 = (editingSub.lpn1 || '').trim();
    const newLpn2 = (editingSub.lpn2 || '').trim();
    const newLpn3 = (editingSub.lpn3 || '').trim();
    const newPresent = editingSub.resetPresence ? false : editingSub.present;
    const payload = {
      contract_id: selectedCompany.id,
      subscriber_id: editingSub.id,
      first_name: newFirstName,
      last_name: newLastName,
      lpn1: newLpn1,
      lpn2: newLpn2,
      lpn3: newLpn3,
      valid_from: editingSub.valid_from ?? editingSub.validFrom ?? '',
      valid_until: editingSub.valid_until ?? editingSub.validUntil ?? '',
      match_code: editingSub.match_code ?? editingSub.matchCode ?? '',
      memo: editingSub.memo || '',
      present: newPresent
    };
    setSavingSubLoading(true);
    try {
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(`${LOCAL_DEV_API_URL}/subscriber/update`, payload, {
            headers: apiHeaders(),
            timeout: 8000
          });
          if (rLoc.data?.success) resData = rLoc.data;
        } catch (eLoc) {}
      }
      if (!resData?.success) {
        try {
          const res = await axios.post(`${API_BASE_URL}/subscriber/update`, payload, {
            headers: apiHeaders(),
            timeout: 15000
          });
          if (res.data) resData = res.data;
        } catch (eRem) {}
      }
      if (resData?.success) {
        const updatedFullName = `${newLastName} ${newFirstName}`.trim() || editingSub.full_name || editingSub.name;
        const targetSubId = String(editingSub.id);
        setSubscribers((prev) =>
          prev.map((s) =>
            String(s.id) === targetSubId
              ? {
                  ...s,
                  first_name: newFirstName,
                  firstName: newFirstName,
                  last_name: newLastName,
                  lastName: newLastName,
                  full_name: updatedFullName,
                  name: updatedFullName,
                  lpn1: newLpn1,
                  lpn2: newLpn2,
                  lpn3: newLpn3,
                  present: newPresent,
                  isPresent: newPresent
                }
              : s
          )
        );
        setEditingSub(null);
        Alert.alert('נשמר בהצלחה ✓', resData.message || 'פרטי המנוי עודכנו מיידית ונרשמו ביומן האירועים');
      } else {
        Alert.alert('שגיאה', resData?.message || 'עדכון מנוי נכשל');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'עדכון מנוי נכשל');
    } finally {
      setSavingSubLoading(false);
    }
  };

  // =====================================================
  // TAB 4: VEHICLE SEARCH (PATROL + TRANSIENT FEE)
  // =====================================================
  const runVehicleSearch = async (overridePlate = null) => {
    const plate = (overridePlate || searchPlateInput || '').replace(/[^A-Za-z0-9מ]/g, '').toUpperCase();
    if (plate.length < 3) {
      Alert.alert('שגיאה', 'נא להקליד לפחות 3 ספרות של מספר הרכב');
      return;
    }
    if (overridePlate) setSearchPlateInput(overridePlate);
    setSearchLoading(true);
    try {
      let resData = null;
      if (LOCAL_DEV_API_URL) {
        try {
          const rLoc = await axios.post(
            `${LOCAL_DEV_API_URL}/search-vehicle`,
            { plate },
            { headers: apiHeaders(), timeout: 8000 }
          );
          if (rLoc.data?.success) resData = rLoc.data;
        } catch (eLoc) {}
      }
      if (!resData) {
        try {
          const res = await axios.post(
            `${API_BASE_URL}/search-vehicle`,
            { plate },
            { headers: apiHeaders(), timeout: 15000 }
          );
          if (res.data?.success) resData = res.data;
        } catch (eRem) {}
      }
      if (resData?.success) {
        setSearchResult(resData);
      } else {
        Alert.alert('שגיאה', resData?.message || 'חיפוש נכשל');
      }
    } catch (err) {
      Alert.alert('שגיאה', err.response?.data?.message || 'חיפוש רכב נכשל');
    } finally {
      setSearchLoading(false);
    }
  };

  // =====================================================
  // RENDER: LOGIN SCREEN (SENSITIVE OTP + MULTI-PARKING)
  // =====================================================
  if (!authToken) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={styles.safeArea}>
          <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          >
            <ScrollView
              contentContainerStyle={styles.authScroll}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
                <View style={[styles.authCard, isTablet && { maxWidth: 480 }]}>
                  <Image
                    source={require('./assets/icon.png')}
                    style={{
                      width: 80,
                      height: 80,
                      borderRadius: 20,
                      marginBottom: 10,
                      borderWidth: 1,
                      borderColor: '#38bdf8'
                    }}
                    resizeMode="cover"
                  />
                  <Text style={styles.authTitle}>בקרה ותפעול חניון</Text>
                  <Text style={styles.authSubtitle}>
                    מערכת רגישה לתפעול מחסומים, בקרת נתיבים, מונים ומנויים.
                  </Text>

                  {!otpStep ? (
                    <View style={{ width: '100%' }}>
                      <Text style={styles.inputLabel}>מספר טלפון נייד של מנהל החניון</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <TouchableOpacity
                          style={styles.kbCheckInlineBtn}
                          onPress={() => Keyboard.dismiss()}
                        >
                          <Text style={styles.kbCheckInlineText}>✓</Text>
                        </TouchableOpacity>
                        <TextInput
                          style={[styles.textInput, { flex: 1, marginBottom: 0 }]}
                          value={phoneInput}
                          onChangeText={(txt) => {
                            setPhoneInput(txt);
                            setLoginParkingChoices([]);
                          }}
                          placeholder="050-0000000"
                          placeholderTextColor="#64748b"
                          keyboardType="phone-pad"
                          returnKeyType="done"
                          blurOnSubmit={true}
                          onSubmitEditing={() => {
                            Keyboard.dismiss();
                            handleSendOtp();
                          }}
                          inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                          textAlign="center"
                        />
                      </View>

                      {loginParkingChoices.length > 1 && (
                        <View style={{ marginTop: 4, marginBottom: 8 }}>
                          <Text style={[styles.inputLabel, { color: '#38bdf8' }]}>
                            🏢 מספר הטלפון משויך ליותר מחניון אחד — בחר חניון:
                          </Text>
                          {loginParkingChoices.map((p) => (
                            <TouchableOpacity
                              key={`${p.project_number}_${p.user_id}`}
                              style={[
                                styles.parkingChoiceBtn,
                                String(selectedProjectNumber) === String(p.project_number) &&
                                  styles.parkingChoiceBtnActive
                              ]}
                              onPress={() => {
                                setSelectedProjectNumber(String(p.project_number));
                                setSelectedUserId(p.user_id);
                                handleSendOtp(String(p.project_number), p.user_id);
                              }}
                            >
                              <View>
                                <Text style={styles.parkingChoiceName}>
                                  {p.parking_name || p.project_name || `חניון ${p.project_number}`}
                                </Text>
                                <Text style={styles.parkingChoiceMeta}>חניון #{p.project_number}</Text>
                              </View>
                              <Text style={{ color: '#38bdf8', fontWeight: '700' }}>בחר ושלח קוד ←</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      )}

                      {loginParkingChoices.length <= 1 && (
                        <TouchableOpacity
                          style={styles.primaryBtn}
                          onPress={() => handleSendOtp()}
                          disabled={authLoading}
                        >
                          {authLoading ? (
                            <ActivityIndicator color="#fff" />
                          ) : (
                            <Text style={styles.primaryBtnText}>📲 שלח קוד אימות ב-WhatsApp</Text>
                          )}
                        </TouchableOpacity>
                      )}
                    </View>
                  ) : (
                    <View style={{ width: '100%' }}>
                      {directOtpCode ? (
                        <TouchableOpacity
                          style={styles.quickOtpBtn}
                          onPress={() => {
                            setOtpInput(directOtpCode);
                            handleVerifyOtp(directOtpCode);
                          }}
                        >
                          <Text style={styles.quickOtpBtnText}>
                            ✨ לחץ כאן לכניסה מהירה ({directOtpCode})
                          </Text>
                        </TouchableOpacity>
                      ) : null}

                      <TouchableOpacity
                        style={[
                          styles.quickOtpBtn,
                          {
                            backgroundColor: 'rgba(56,189,248,0.14)',
                            borderColor: '#38bdf8',
                            marginBottom: 10
                          }
                        ]}
                        onPress={handlePasteOtpFromClipboard}
                      >
                        <Text style={[styles.quickOtpBtnText, { color: '#38bdf8' }]}>
                          📋 הדבק קוד מ-WhatsApp והיכנס מיד
                        </Text>
                      </TouchableOpacity>

                      <Text style={styles.inputLabel}>הזן קוד אימות בן 6 ספרות מ-WhatsApp</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <TouchableOpacity
                          style={styles.kbCheckInlineBtn}
                          onPress={() => Keyboard.dismiss()}
                        >
                          <Text style={styles.kbCheckInlineText}>✓</Text>
                        </TouchableOpacity>
                        <TextInput
                          style={[styles.textInput, styles.otpTextInput, { flex: 1, marginBottom: 0 }]}
                          value={otpInput}
                          onChangeText={(val) => {
                            setOtpInput(val);
                            const clean6 = val.replace(/\D/g, '');
                            if (clean6.length === 6) {
                              handleVerifyOtp(clean6);
                            }
                          }}
                          placeholder="------"
                          placeholderTextColor="#64748b"
                          keyboardType="number-pad"
                          returnKeyType="done"
                          blurOnSubmit={true}
                          onSubmitEditing={() => {
                            Keyboard.dismiss();
                            handleVerifyOtp();
                          }}
                          inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                          maxLength={6}
                          textAlign="center"
                        />
                      </View>

                      <TouchableOpacity
                        style={[styles.primaryBtn, { backgroundColor: '#10b981' }]}
                        onPress={() => handleVerifyOtp()}
                        disabled={authLoading}
                      >
                        {authLoading ? (
                          <ActivityIndicator color="#fff" />
                        ) : (
                          <Text style={styles.primaryBtnText}>🔓 אמת קוד ופתח מסוף תפעול</Text>
                        )}
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.secondaryBtn}
                        onPress={() => {
                          Keyboard.dismiss();
                          setOtpStep(false);
                          setDirectOtpCode('');
                        }}
                      >
                        <Text style={styles.secondaryBtnText}>חזרה להזנת טלפון / החלפת חניון</Text>
                      </TouchableOpacity>
                    </View>
                  )}

                  <View
                    style={{
                      marginTop: 16,
                      paddingTop: 10,
                      borderTopWidth: 1,
                      borderTopColor: '#334155',
                      width: '100%',
                      alignItems: 'center'
                    }}
                  >
                    <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: '700', textAlign: 'center' }}>
                      © 2026 {COPYRIGHT_HOLDER} — כל הזכויות שמורות | גרסה {APP_VERSION}
                    </Text>
                    <Text style={{ color: '#64748b', fontSize: 11, marginTop: 2, textAlign: 'center' }}>
                      שיידט את בכמן ישראל בע"מ
                    </Text>
                  </View>
                </View>
              </TouchableWithoutFeedback>
            </ScrollView>
          </KeyboardAvoidingView>

          {Platform.OS === 'ios' && (
            <InputAccessoryView nativeID={KB_ACCESSORY_ID}>
              <View style={styles.kbAccessoryBar}>
                <TouchableOpacity
                  style={styles.kbAccessoryActionBtn}
                  onPress={() => {
                    Keyboard.dismiss();
                    if (!otpStep) {
                      handleSendOtp();
                    } else {
                      handleVerifyOtp();
                    }
                  }}
                >
                  <Text style={styles.kbAccessoryActionText}>
                    {!otpStep ? '📲 שלח קוד ב-WhatsApp' : '🔓 אמת קוד'}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.kbAccessoryDoneBtn}
                  onPress={() => Keyboard.dismiss()}
                >
                  <Text style={styles.kbAccessoryDoneText}>✓ הורד מקלדת</Text>
                </TouchableOpacity>
              </View>
            </InputAccessoryView>
          )}
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  // Filter lanes (supports direction/category filter AND custom multi-unit selection)
  const selectedUnitKeys = Object.keys(selectedUnitsMap).filter((k) => selectedUnitsMap[k]);
  const hasUnitSelectionFilter = selectedUnitKeys.length > 0;
  const filteredLanes = lanes.filter((l) => {
    const uKey = String(l.number || l.unit);
    if (hasUnitSelectionFilter && !selectedUnitsMap[uKey]) return false;
    if (laneFilter === 'ALL') return true;
    const dir = String(l.direction || l.category || '').toUpperCase();
    if (laneFilter === 'LOCKED') return !!(l.is_locked || l.barrier_locked || l.is_out_of_order);
    return dir === laneFilter;
  });

  // Group filtered lanes by parking facility (sorted: entries first, then exits per facility)
  const groupedLanesByFacility = [];
  const facGroupMap = {};
  filteredLanes.forEach((ln) => {
    const fId = String(ln.facility_number || '1');
    const fName = ln.facility_name || `חניון ${fId}`;
    if (!facGroupMap[fId]) {
      facGroupMap[fId] = { facility_number: fId, facility_name: fName, lanes: [] };
      groupedLanesByFacility.push(facGroupMap[fId]);
    }
    facGroupMap[fId].lanes.push(ln);
  });

  // Dynamic grid columns based on orientation & device width
  const lanePaneWidth = isSplitLayout ? width * 0.56 : width;
  const numLaneColumns = lanePaneWidth >= 700 ? 3 : lanePaneWidth >= 340 ? 2 : 1;
  const cardWidthPct = numLaneColumns === 3 ? '31.8%' : numLaneColumns === 2 ? '48.2%' : '100%';

  const laneImageUrl = selectedUnit
    ? laneDetail?.image_url
      ? `${SERVER_URL}${laneDetail.image_url}&auth_token=${encodeURIComponent(authToken)}&cb=${imageCacheBust}`
      : `${API_BASE_URL}/lane-image/${selectedUnit}?auth_token=${encodeURIComponent(authToken)}&project_number=${encodeURIComponent(userProfile?.project_number || '')}&cb=${imageCacheBust}`
    : null;

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="#0f172a" />

        {/* TOP BAR */}
        <View style={styles.topBar}>
          <View style={styles.topBarRight}>
            <Image
              source={require('./assets/icon.png')}
              style={{ width: 34, height: 34, borderRadius: 8, borderWidth: 1, borderColor: '#38bdf8' }}
              resizeMode="cover"
            />
            <View style={styles.liveDot} />
            <View style={{ flex: 1 }}>
              <Text style={styles.topBarTitle} numberOfLines={1}>
                {userProfile?.parking_name || userProfile?.project_name || 'חניון פעיל'}
              </Text>
              <Text style={styles.topBarSub}>
                {userProfile?.username} • #{userProfile?.project_number}
              </Text>
            </View>
          </View>

          <View style={styles.topBarActions}>
            {parkingOptions.length > 1 && (
              <TouchableOpacity
                style={styles.switchParkingBtn}
                onPress={() => setParkingChoiceModal(true)}
              >
                <Text style={styles.switchParkingBtnText}>🏢 החלף חניון ({parkingOptions.length})</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={() => {
                if (activeTab === 'ops') {
                  loadOverview(false, null, true);
                  if (selectedUnit) selectLane(selectedUnit, false);
                }
                if (activeTab === 'counters') loadCounters();
                if (activeTab === 'companies') loadCompanies();
              }}
            >
              <Text style={{ fontSize: 16 }}>🔄</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.iconBtn, { borderColor: '#ef4444' }]}
              onPress={handleLogout}
            >
              <Text style={{ fontSize: 15 }}>🔒</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* MAIN CONTENT AREA */}
        <View style={{ flex: 1 }}>
          {/* ================= TAB 1: OPERATIONS ================= */}
          {activeTab === 'ops' && (
            <View style={[styles.opsContainer, isSplitLayout && { flexDirection: 'row-reverse' }]}>
              {/* Lanes Grid Pane */}
              <View style={{ flex: isSplitLayout ? 1.3 : 1 }}>
                {/* Category Filter Chips + Custom Unit Selection Button */}
                <View style={styles.filterRow}>
                  {[
                    { key: 'ALL', label: `הכל (${hasUnitSelectionFilter ? `${filteredLanes.length}/${lanes.length}` : lanes.length})` },
                    { key: 'ENTRY', label: '🟢 כניסות' },
                    { key: 'EXIT', label: '🔴 יציאות' },
                    { key: 'PASSAGE', label: '🟡 מעברים' },
                    { key: 'LOCKED', label: '🔒 נעולים' }
                  ].map((f) => (
                    <TouchableOpacity
                      key={f.key}
                      style={[styles.filterChip, laneFilter === f.key && styles.filterChipActive]}
                      onPress={() => setLaneFilter(f.key)}
                    >
                      <Text style={[styles.filterChipText, laneFilter === f.key && { color: '#fff' }]}>
                        {f.label}
                      </Text>
                    </TouchableOpacity>
                  ))}

                  <TouchableOpacity
                    style={[
                      styles.filterChip,
                      {
                        borderColor: hasUnitSelectionFilter ? '#38bdf8' : '#475569',
                        backgroundColor: hasUnitSelectionFilter ? 'rgba(56,189,248,0.22)' : '#1e293b'
                      }
                    ]}
                    onPress={() => setUnitSelectorModal(true)}
                  >
                    <Text
                      style={[
                        styles.filterChipText,
                        { color: hasUnitSelectionFilter ? '#38bdf8' : '#e2e8f0', fontWeight: '800' }
                      ]}
                    >
                      {hasUnitSelectionFilter
                        ? `☑️ יחידות נבחרות (${selectedUnitKeys.length})`
                        : '☑️ בחירת יחידות'}
                    </Text>
                  </TouchableOpacity>

                  {hasUnitSelectionFilter && (
                    <TouchableOpacity
                      style={[styles.filterChip, { borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.16)' }]}
                      onPress={clearUnitSelectionFilter}
                    >
                      <Text style={[styles.filterChipText, { color: '#fca5a5', fontWeight: '800' }]}>
                        ✕ הצג הכל
                      </Text>
                    </TouchableOpacity>
                  )}
                </View>

                <ScrollView
                  contentContainerStyle={{ paddingHorizontal: 10, paddingBottom: 14 }}
                  refreshControl={
                    <RefreshControl
                      refreshing={refreshing}
                      onRefresh={() => loadOverview(false, null, true)}
                      tintColor="#38bdf8"
                    />
                  }
                >
                  {groupedLanesByFacility.map((facGroup) => (
                    <View key={`fac_grp_${facGroup.facility_number}`} style={{ marginBottom: 12 }}>
                      {/* Parking Facility Section Header */}
                      <View
                        style={{
                          flexDirection: 'row-reverse',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          backgroundColor: 'rgba(30,41,59,0.9)',
                          borderRightWidth: 3,
                          borderRightColor: '#38bdf8',
                          borderRadius: 9,
                          paddingHorizontal: 12,
                          paddingVertical: 6,
                          marginBottom: 8
                        }}
                      >
                        <Text style={{ color: '#f8fafc', fontSize: 13.5, fontWeight: '800', textAlign: 'right' }}>
                          🅿️ {facGroup.facility_name} (#{facGroup.facility_number})
                        </Text>
                        <Text style={{ color: '#38bdf8', fontSize: 11.5, fontWeight: '700' }}>
                          {facGroup.lanes.length} יחידות
                        </Text>
                      </View>

                      <View style={styles.lanesGrid}>
                        {facGroup.lanes.map((lane) => {
                          const unitId = String(lane.number || lane.unit);
                          const isLocked = !!(lane.is_locked || lane.barrier_locked);
                          const isSelected = String(selectedUnit) === unitId;
                          const statusLabel =
                            lane.device_state_label ||
                            lane.status_summary_he ||
                            (lane.is_barrier_open ? 'פתוח' : 'תקין');
                          const typeHe =
                            lane.type_label_he ||
                            lane.category_he ||
                            (lane.direction === 'exit' ? 'יציאה' : lane.direction === 'passage' ? 'מעבר' : 'כניסה');
                          const displayPlate = lane.formatted_plate || lane.last_plate || '';

                          return (
                            <TouchableOpacity
                              key={unitId}
                              style={[
                                styles.laneCard,
                                { width: cardWidthPct },
                                isSelected && styles.laneCardSelected,
                                isLocked && styles.laneCardLocked
                              ]}
                              onPress={() => selectLane(unitId)}
                              activeOpacity={0.85}
                            >
                              <View style={styles.laneCardHeader}>
                                <View style={{ flex: 1 }}>
                                  <Text style={styles.laneName} numberOfLines={1}>
                                    {lane.name}
                                  </Text>
                                  <Text style={styles.laneUnitText} numberOfLines={1}>
                                    יחידה {unitId} • {typeHe}
                                  </Text>
                                </View>
                                <View
                                  style={[
                                    styles.statusBadge,
                                    isLocked
                                      ? { backgroundColor: 'rgba(239,68,68,0.2)' }
                                      : { backgroundColor: 'rgba(16,185,129,0.18)' }
                                  ]}
                                >
                                  <Text
                                    style={{
                                      fontSize: 10,
                                      fontWeight: '700',
                                      color: isLocked ? '#fca5a5' : '#6ee7b7'
                                    }}
                                  >
                                    {statusLabel}
                                  </Text>
                                </View>
                              </View>

                              <View style={styles.lanePlateRow}>
                                {displayPlate ? (
                                  <View style={styles.ilPlateMini}>
                                    <Text style={styles.ilPlateMiniText} numberOfLines={1}>
                                      {displayPlate}
                                    </Text>
                                  </View>
                                ) : (
                                  <Text style={{ fontSize: 11, color: '#64748b' }}>לחץ לבדיקת רכב אחרון</Text>
                                )}
                              </View>

                              <View style={styles.laneQuickBtns}>
                                <TouchableOpacity
                                  style={[styles.qBtn, { backgroundColor: '#10b981' }]}
                                  onPress={() => sendLaneCommand(lane, 'OPEN', 'פתיחת מחסום')}
                                >
                                  <Text style={styles.qBtnText} numberOfLines={1} adjustsFontSizeToFit>
                                    🔼 פתח
                                  </Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                  style={[styles.qBtn, { backgroundColor: '#334155' }]}
                                  onPress={() => sendLaneCommand(lane, 'CLOSE', 'סגירת מחסום')}
                                >
                                  <Text style={styles.qBtnText} numberOfLines={1} adjustsFontSizeToFit>
                                    🔽 סגור
                                  </Text>
                                </TouchableOpacity>
                                {isLocked ? (
                                  <TouchableOpacity
                                    style={[styles.qBtn, { backgroundColor: '#f59e0b' }]}
                                    onPress={() => sendLaneCommand(lane, 'UNLOCK_BARRIER', 'שחרור נעילה')}
                                  >
                                    <Text style={styles.qBtnText} numberOfLines={1} adjustsFontSizeToFit>
                                      🔓 שחרר
                                    </Text>
                                  </TouchableOpacity>
                                ) : (
                                  <TouchableOpacity
                                    style={[styles.qBtn, { backgroundColor: '#7f1d1d' }]}
                                    onPress={() => sendLaneCommand(lane, 'LOCK_BARRIER', 'נעילת מחסום')}
                                  >
                                    <Text style={styles.qBtnText} numberOfLines={1} adjustsFontSizeToFit>
                                      🔒 נעל
                                    </Text>
                                  </TouchableOpacity>
                                )}
                              </View>

                              {(lane.direction === 'exit' || (parseInt(unitId, 10) >= 200 && parseInt(unitId, 10) <= 299)) && (
                                <TouchableOpacity
                                  style={{
                                    marginTop: 6,
                                    backgroundColor: '#1e293b',
                                    borderWidth: 1,
                                    borderColor: '#38bdf8',
                                    borderRadius: 8,
                                    paddingVertical: 6,
                                    alignItems: 'center'
                                  }}
                                  onPress={() => openExitPriceModalFromCard(lane)}
                                >
                                  <Text style={{ color: '#38bdf8', fontSize: 11.5, fontWeight: '800' }}>
                                    💳 בדיקה ושליחת מחיר לצג
                                  </Text>
                                </TouchableOpacity>
                              )}
                            </TouchableOpacity>
                          );
                        })}
                      </View>
                    </View>
                  ))}
                </ScrollView>
              </View>

              {/* Side-by-Side Inspector on Tablet/Landscape */}
              {isSplitLayout && selectedUnit && (
                <View style={styles.splitInspectorPane}>{renderLaneInspector()}</View>
              )}
            </View>
          )}

          {/* ================= TAB 2: ONLINE COUNTERS & DAILY REPORTS ================= */}
          {activeTab === 'counters' && (
            <ScrollView
              contentContainerStyle={{ padding: 14 }}
              keyboardShouldPersistTaps="handled"
              refreshControl={
                <RefreshControl
                  refreshing={countersLoading}
                  onRefresh={() => loadCounters()}
                  tintColor="#38bdf8"
                />
              }
            >
              {/* TOP SECTION: PER-PARKING PRESENT CARS (RESERVED VS NOT RESERVED ONLY) */}
              {(countersData?.facilities || [])
                .filter((fac) => {
                  const allFacCounters =
                    fac.counters || (fac.standard_counters || []).concat(fac.level_counters || []);
                  const cNotReserved = allFacCounters.find((c) => String(c.id) === '1');
                  const cReserved = allFacCounters.find((c) => String(c.id) === '2');
                  if (!cNotReserved && !cReserved) return false;
                  const p1 = cNotReserved ? Number(cNotReserved.present || 0) : 0;
                  const p2 = cReserved ? Number(cReserved.present || 0) : 0;
                  // Always show main facility 3050 & 3200, or any facility with present > 0
                  return String(fac.facility_id) === '3050' || String(fac.facility_id) === '3200' || p1 + p2 > 0;
                })
                .map((fac) => {
                const allFacCounters =
                  fac.counters || (fac.standard_counters || []).concat(fac.level_counters || []);
                const cNotReserved = allFacCounters.find((c) => String(c.id) === '1');
                const cReserved = allFacCounters.find((c) => String(c.id) === '2');
                const presentTransient = cNotReserved ? Number(cNotReserved.present || 0) : 0;
                const presentSubscribers = cReserved ? Number(cReserved.present || 0) : 0;
                const totalFacilityPresent = presentTransient + presentSubscribers;

                return (
                  <View key={fac.facility_id} style={styles.sectionCard}>
                    <View
                      style={{
                        flexDirection: 'row-reverse',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 10
                      }}
                    >
                      <Text style={[styles.sectionTitle, { marginBottom: 0, flex: 1 }]}>
                        🅿️ {fac.facility_name}
                      </Text>
                      <View
                        style={{
                          backgroundColor: 'rgba(56,189,248,0.16)',
                          borderWidth: 1,
                          borderColor: '#38bdf8',
                          borderRadius: 9,
                          paddingHorizontal: 10,
                          paddingVertical: 4
                        }}
                      >
                        <Text style={{ color: '#38bdf8', fontWeight: '800', fontSize: 12 }}>
                          סה״כ נוכחים: {totalFacilityPresent}
                        </Text>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', gap: 8 }}>
                      {/* Reserved (Subscribers) Present */}
                      {cReserved && (
                        <View
                          style={{
                            flex: 1,
                            backgroundColor: '#0f172a',
                            borderRadius: 12,
                            padding: 10,
                            borderWidth: 1,
                            borderColor: '#334155',
                            alignItems: 'center'
                          }}
                        >
                          <Text style={{ color: '#94a3b8', fontSize: 11.5, fontWeight: '700' }}>
                            שמורים (מנויים)
                          </Text>
                          <Text style={{ color: '#38bdf8', fontSize: 24, fontWeight: '900', marginVertical: 4 }}>
                            {presentSubscribers}
                          </Text>
                          <Text
                            style={{
                              fontSize: 11,
                              fontWeight: '700',
                              color: cReserved.status_value ? '#ef4444' : '#10b981',
                              marginBottom: 8
                            }}
                          >
                            {cReserved.status_label || cReserved.occupied_he || 'פנוי'}
                          </Text>
                          <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 4, justifyContent: 'center' }}>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cReserved.id, 'occupiedstate', 0)}
                            >
                              <Text style={styles.miniActionText}>🟢 פנוי</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cReserved.id, 'occupiedstate', 1)}
                            >
                              <Text style={styles.miniActionText}>🔴 מלא</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cReserved.id, 'increasefreeplaces', 1)}
                            >
                              <Text style={styles.miniActionText}>+1</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cReserved.id, 'decreasefreeplaces', 1)}
                            >
                              <Text style={styles.miniActionText}>-1</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      )}

                      {/* Not Reserved (Transient) Present */}
                      {cNotReserved && (
                        <View
                          style={{
                            flex: 1,
                            backgroundColor: '#0f172a',
                            borderRadius: 12,
                            padding: 10,
                            borderWidth: 1,
                            borderColor: '#334155',
                            alignItems: 'center'
                          }}
                        >
                          <Text style={{ color: '#94a3b8', fontSize: 11.5, fontWeight: '700' }}>
                            לא שמורים (מזדמנים)
                          </Text>
                          <Text style={{ color: '#10b981', fontSize: 24, fontWeight: '900', marginVertical: 4 }}>
                            {presentTransient}
                          </Text>
                          <Text
                            style={{
                              fontSize: 11,
                              fontWeight: '700',
                              color: cNotReserved.status_value ? '#ef4444' : '#10b981',
                              marginBottom: 8
                            }}
                          >
                            {cNotReserved.status_label || cNotReserved.occupied_he || 'פנוי'}
                          </Text>
                          <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 4, justifyContent: 'center' }}>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cNotReserved.id, 'occupiedstate', 0)}
                            >
                              <Text style={styles.miniActionText}>🟢 פנוי</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cNotReserved.id, 'occupiedstate', 1)}
                            >
                              <Text style={styles.miniActionText}>🔴 מלא</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cNotReserved.id, 'increasefreeplaces', 1)}
                            >
                              <Text style={styles.miniActionText}>+1</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              style={styles.miniActionBtn}
                              onPress={() => updateCounterAction(fac.facility_id, cNotReserved.id, 'decreasefreeplaces', 1)}
                            >
                              <Text style={styles.miniActionText}>-1</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      )}
                    </View>
                  </View>
                );
              })}

              {/* BELOW COUNTERS: LIVE & HISTORICAL DAILY REPORT (FLEXREP / UDB / SUPABASE) */}
              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>💰 דוח הכנסות, תשלומים ותנועות רכבים</Text>
                <Text style={{ color: '#38bdf8', fontSize: 11.5, textAlign: 'right', marginBottom: 10 }}>
                  תאריך: {dailyReportData?.date_display || (isDateRangeMode ? `${reportDateInput} עד ${reportEndDateInput}` : reportDateInput)} • מקור:{' '}
                  {dailyReportData?.source_label_he || 'שרת החניון'}
                </Text>

                {/* Quick Range & Mode Buttons */}
                <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginBottom: 8 }}>
                  <TouchableOpacity
                    style={[styles.filterChip, !isDateRangeMode && reportDateInput === new Date().toISOString().slice(0, 10) && styles.filterChipActive]}
                    onPress={() => shiftReportDate(0)}
                  >
                    <Text style={[styles.filterChipText, !isDateRangeMode && reportDateInput === new Date().toISOString().slice(0, 10) && { color: '#fff' }]}>
                      היום
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.filterChip}
                    onPress={() => shiftReportDate(-1)}
                  >
                    <Text style={styles.filterChipText}>אתמול</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.filterChip, isDateRangeMode && styles.filterChipActive]}
                    onPress={() => selectLast7DaysRange()}
                  >
                    <Text style={[styles.filterChipText, isDateRangeMode && { color: '#fff' }]}>7 ימים</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[
                      styles.filterChip,
                      {
                        borderColor: isDateRangeMode ? '#38bdf8' : '#475569',
                        backgroundColor: isDateRangeMode ? 'rgba(56,189,248,0.18)' : '#0f172a'
                      }
                    ]}
                    onPress={() => {
                      const nextMode = !isDateRangeMode;
                      setIsDateRangeMode(nextMode);
                      if (nextMode && reportEndDateInput === reportDateInput) {
                        const prevDt = new Date(reportDateInput);
                        if (!isNaN(prevDt.getTime())) {
                          prevDt.setDate(prevDt.getDate() - 6);
                          const sIso = prevDt.toISOString().slice(0, 10);
                          setReportDateInput(sIso);
                          loadDailyReportOnly(sIso, reportEndDateInput);
                        }
                      } else if (!nextMode) {
                        setReportEndDateInput(reportDateInput);
                        loadDailyReportOnly(reportDateInput, reportDateInput);
                      }
                    }}
                  >
                    <Text style={[styles.filterChipText, { color: isDateRangeMode ? '#38bdf8' : '#cbd5e1' }]}>
                      {isDateRangeMode ? '📆 טווח תאריכים פעיל ✓' : '📆 בחר טווח תאריכים'}
                    </Text>
                  </TouchableOpacity>
                </View>

                {/* Calendar Date Buttons Row - Clear Stacked Layout for Range Mode */}
                {!isDateRangeMode ? (
                  <View style={{ flexDirection: 'row-reverse', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                    <TouchableOpacity
                      style={{
                        flex: 1,
                        flexDirection: 'row-reverse',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        backgroundColor: '#0f172a',
                        borderWidth: 1,
                        borderColor: '#38bdf8',
                        borderRadius: 11,
                        paddingHorizontal: 14,
                        paddingVertical: 11
                      }}
                      onPress={() => openCalendarPicker('start')}
                    >
                      <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: '700' }}>תאריך דוח:</Text>
                      <Text style={{ color: '#f8fafc', fontSize: 15, fontWeight: '800' }}>
                        📅 {reportDateInput}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.quotaSaveBtn, { paddingVertical: 11, paddingHorizontal: 16 }]}
                      onPress={() => loadDailyReportOnly(reportDateInput, reportDateInput)}
                      disabled={reportLoading}
                    >
                      <Text style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}>
                        {reportLoading ? '...' : '📊 הצג'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <View style={{ marginBottom: 10, gap: 8 }}>
                    <View style={{ flexDirection: 'row-reverse', gap: 8 }}>
                      <TouchableOpacity
                        style={{
                          flex: 1,
                          backgroundColor: '#0f172a',
                          borderWidth: 1,
                          borderColor: '#38bdf8',
                          borderRadius: 11,
                          paddingVertical: 8,
                          paddingHorizontal: 10,
                          alignItems: 'center'
                        }}
                        onPress={() => openCalendarPicker('start')}
                      >
                        <Text style={{ color: '#94a3b8', fontSize: 11, fontWeight: '700', marginBottom: 2 }}>
                          מתאריך (התחלה):
                        </Text>
                        <Text style={{ color: '#f8fafc', fontSize: 14.5, fontWeight: '900' }} numberOfLines={1}>
                          📅 {reportDateInput}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={{
                          flex: 1,
                          backgroundColor: '#0f172a',
                          borderWidth: 1,
                          borderColor: '#38bdf8',
                          borderRadius: 11,
                          paddingVertical: 8,
                          paddingHorizontal: 10,
                          alignItems: 'center'
                        }}
                        onPress={() => openCalendarPicker('end')}
                      >
                        <Text style={{ color: '#94a3b8', fontSize: 11, fontWeight: '700', marginBottom: 2 }}>
                          עד תאריך (סיום):
                        </Text>
                        <Text style={{ color: '#f8fafc', fontSize: 14.5, fontWeight: '900' }} numberOfLines={1}>
                          📅 {reportEndDateInput}
                        </Text>
                      </TouchableOpacity>
                    </View>

                    <TouchableOpacity
                      style={[styles.quotaSaveBtn, { width: '100%', paddingVertical: 11, alignItems: 'center' }]}
                      onPress={() => loadDailyReportOnly(reportDateInput, reportEndDateInput)}
                      disabled={reportLoading}
                    >
                      <Text style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}>
                        {reportLoading ? '⏳ טוען דוח לטווח תאריכים...' : `📊 הצג דוח (${reportDateInput} עד ${reportEndDateInput})`}
                      </Text>
                    </TouchableOpacity>
                  </View>
                )}

                {dailyReportData?.recent_days?.length > 0 && (
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={{ flexDirection: 'row-reverse', gap: 6, marginBottom: 12 }}
                  >
                    {dailyReportData.recent_days.map((dItem) => {
                      const active = !dailyReportData.is_range && dItem.date === dailyReportData.report_date;
                      return (
                        <TouchableOpacity
                          key={dItem.date}
                          style={[styles.filterChip, active && styles.filterChipActive]}
                          onPress={() => {
                            setIsDateRangeMode(false);
                            setReportDateInput(dItem.date);
                            setReportEndDateInput(dItem.date);
                            loadDailyReportOnly(dItem.date, dItem.date);
                          }}
                        >
                          <Text style={[styles.filterChipText, active && { color: '#fff' }]}>
                            {dItem.date.slice(5)} • ₪{Number(dItem.revenue_ils || 0).toFixed(0)} ({dItem.entries} כנ׳)
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </ScrollView>
                )}

                {dailyReportData ? (
                  <View>
                    <View style={styles.kpiRow}>
                      {/* Total Revenue (POS + Pango + Cellopark) */}
                      <View
                        style={[
                          styles.kpiBox,
                          { borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.12)' }
                        ]}
                      >
                        <Text style={[styles.kpiVal, { color: '#34d399', fontSize: 19 }]}>
                          ₪{Number(dailyReportData.revenue?.total_revenue_ils || 0).toFixed(2)}
                        </Text>
                        <Text style={[styles.kpiLbl, { color: '#6ee7b7', fontWeight: '700' }]}>
                          סה״כ הכנסות בחניון
                        </Text>
                        <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 2, textAlign: 'center' }}>
                          נטו: ₪{Number(dailyReportData.revenue?.net_revenue_no_vat_ils || 0).toFixed(1)} | מע״מ: ₪
                          {Number(dailyReportData.revenue?.vat_ils || 0).toFixed(1)}
                        </Text>
                      </View>

                      {/* Paid Vehicles Count (instead of ambiguous "עסקאות בתשלום") */}
                      <View style={styles.kpiBox}>
                        <Text style={[styles.kpiVal, { color: '#fbbf24', fontSize: 19 }]}>
                          {dailyReportData.revenue?.paid_transactions_count || 0}
                        </Text>
                        <Text style={[styles.kpiLbl, { fontWeight: '700' }]}>רכבים ששילמו</Text>
                        <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 2, textAlign: 'center' }}>
                          קופות: {dailyReportData.revenue?.pos_paid_count ?? dailyReportData.revenue?.paid_transactions_count ?? 0} | אפל׳:{' '}
                          {Number(dailyReportData.revenue?.pango_count || 0) + Number(dailyReportData.revenue?.cello_count || 0)}
                        </Text>
                      </View>

                      {/* Total Entries across ALL sub-parkings */}
                      <View style={styles.kpiBox}>
                        <Text style={[styles.kpiVal, { color: '#38bdf8', fontSize: 19 }]}>
                          {dailyReportData.traffic?.entries_total || 0}
                        </Text>
                        <Text style={[styles.kpiLbl, { fontWeight: '700' }]}>🟢 סה״כ כניסות (כל החניונים)</Text>
                        <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 2, textAlign: 'center' }}>
                          מזדמן: {dailyReportData.traffic?.entries_transient || 0} | מנוי:{' '}
                          {dailyReportData.traffic?.entries_subscribers || 0} | אפל׳:{' '}
                          {dailyReportData.traffic?.entries_app_external || 0}
                        </Text>
                      </View>

                      {/* Total Exits across ALL sub-parkings */}
                      <View style={styles.kpiBox}>
                        <Text style={[styles.kpiVal, { color: '#c084fc', fontSize: 19 }]}>
                          {dailyReportData.traffic?.exits_total || 0}
                        </Text>
                        <Text style={[styles.kpiLbl, { fontWeight: '700' }]}>🔴 סה״כ יציאות (כל החניונים)</Text>
                        <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 2, textAlign: 'center' }}>
                          מזדמן: {dailyReportData.traffic?.exits_transient || 0} | מנוי:{' '}
                          {dailyReportData.traffic?.exits_subscribers || 0} | חסד:{' '}
                          {dailyReportData.traffic?.exits_grace_free || 0}
                        </Text>
                      </View>
                    </View>

                    {/* Manual Barrier Openings & Discounts Banner */}
                    <View
                      style={{
                        flexDirection: 'row-reverse',
                        justifyContent: 'space-between',
                        gap: 8,
                        marginBottom: 12
                      }}
                    >
                      <View
                        style={{
                          flex: 1,
                          backgroundColor: '#0f172a',
                          borderRadius: 11,
                          paddingVertical: 9,
                          paddingHorizontal: 10,
                          borderWidth: 1,
                          borderColor: '#38bdf8',
                          alignItems: 'center'
                        }}
                      >
                        <Text style={{ color: '#38bdf8', fontSize: 18, fontWeight: '900' }}>
                          🚧 {dailyReportData.traffic?.barrier_manual_opens || 0}
                        </Text>
                        <Text style={{ color: '#e2e8f0', fontSize: 11, fontWeight: '700', marginTop: 2 }}>
                          פתיחות מחסום ידניות
                        </Text>
                        {dailyReportData.traffic?.user_audit_actions > 0 && (
                          <Text style={{ color: '#94a3b8', fontSize: 9.5, marginTop: 1 }}>
                            פעולות מפעיל ביומן: {dailyReportData.traffic.user_audit_actions}
                          </Text>
                        )}
                      </View>

                      <View
                        style={{
                          flex: 1,
                          backgroundColor: '#0f172a',
                          borderRadius: 11,
                          paddingVertical: 9,
                          paddingHorizontal: 10,
                          borderWidth: 1,
                          borderColor: '#334155',
                          alignItems: 'center'
                        }}
                      >
                        <Text style={{ color: '#fbbf24', fontSize: 18, fontWeight: '900' }}>
                          ₪{Math.abs(Number(dailyReportData.revenue?.discounts_total_ils || 0)).toFixed(0)}
                        </Text>
                        <Text style={{ color: '#e2e8f0', fontSize: 11, fontWeight: '700', marginTop: 2 }}>
                          שוברים והנחות שמומשו
                        </Text>
                        <Text style={{ color: '#94a3b8', fontSize: 9.5, marginTop: 1 }}>
                          מעברים פנימיים: {dailyReportData.traffic?.internal_passages || 0}
                        </Text>
                      </View>
                    </View>

                    {/* 4 Main Payment Channels: Cash, Credit, Pango, Cellopark */}
                    <View style={{ marginBottom: 12 }}>
                      <Text style={styles.subSectionTitle}>
                        💵💳 הכנסות לפי אמצעי תשלום (מזומן, אשראי, פנגו וסלופארק)
                      </Text>
                      <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', justifyContent: 'space-between', gap: 6 }}>
                        {[
                          {
                            label: '💵 מזומן בקופות',
                            val: Number(dailyReportData.revenue?.cash_ils || 0),
                            cnt: 0,
                            color: '#34d399'
                          },
                          {
                            label: '💳 כרטיסי אשראי',
                            val: Number(dailyReportData.revenue?.credit_ils ?? dailyReportData.revenue?.pos_turnover_ils ?? 0),
                            cnt: Number(dailyReportData.revenue?.pos_paid_count || 0),
                            color: '#38bdf8'
                          },
                          {
                            label: '🅿️ פנגו (Pango)',
                            val: Number(dailyReportData.revenue?.pango_ils || 0),
                            cnt: Number(dailyReportData.revenue?.pango_count || 0),
                            color: '#60a5fa'
                          },
                          {
                            label: '📱 סלופארק (Cello)',
                            val: Number(dailyReportData.revenue?.cello_ils || 0),
                            cnt: Number(dailyReportData.revenue?.cello_count || 0),
                            color: '#c084fc'
                          }
                        ].map((ch, idx) => (
                          <View
                            key={idx}
                            style={{
                              width: '48.5%',
                              backgroundColor: '#0f172a',
                              borderRadius: 10,
                              paddingVertical: 8,
                              paddingHorizontal: 10,
                              borderWidth: 1,
                              borderColor: '#334155',
                              marginBottom: 4
                            }}
                          >
                            <Text style={{ color: '#cbd5e1', fontSize: 11.5, fontWeight: '700', textAlign: 'right' }}>
                              {ch.label}
                            </Text>
                            <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
                              <Text style={{ color: ch.color, fontSize: 16, fontWeight: '900' }}>
                                ₪{ch.val.toFixed(2)}
                              </Text>
                              {ch.cnt > 0 && (
                                <Text style={{ color: '#94a3b8', fontSize: 10.5 }}>
                                  {ch.cnt} רכבים
                                </Text>
                              )}
                            </View>
                          </View>
                        ))}
                      </View>
                    </View>

                    {/* Per-Facility Traffic Breakdown when multiple facilities exist */}
                    {dailyReportData.facilities_traffic?.length > 1 && (
                      <View style={{ marginBottom: 12 }}>
                        <Text style={styles.subSectionTitle}>
                          🏢 פירוט כניסות ויציאות לפי מתחם / חניון (סה״כ מחובר למעלה)
                        </Text>
                        {dailyReportData.facilities_traffic.map((ft, idx) => (
                          <View
                            key={idx}
                            style={{
                              backgroundColor: '#0f172a',
                              borderRadius: 10,
                              padding: 10,
                              borderWidth: 1,
                              borderColor: '#1e293b',
                              marginBottom: 6
                            }}
                          >
                            <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                              <Text style={{ color: '#f8fafc', fontSize: 13, fontWeight: '800', textAlign: 'right', flex: 1 }}>
                                🅿️ {ft.facility_name}
                              </Text>
                              {ft.pos_revenue_ils > 0 && (
                                <Text style={{ color: '#34d399', fontSize: 12, fontWeight: '800' }}>
                                  קופות: ₪{Number(ft.pos_revenue_ils).toFixed(1)}
                                </Text>
                              )}
                            </View>
                            <View style={{ gap: 4 }}>
                              <Text style={{ color: '#38bdf8', fontSize: 12, fontWeight: '700', textAlign: 'right' }}>
                                🟢 כניסות: {ft.entries_total} (מזדמן: {ft.entries_transient} | מנוי: {ft.entries_subscribers})
                              </Text>
                              <Text style={{ color: '#c084fc', fontSize: 12, fontWeight: '700', textAlign: 'right' }}>
                                🔴 יציאות: {ft.exits_total} (מזדמן: {ft.exits_transient} | מנוי: {ft.exits_subscribers})
                              </Text>
                            </View>
                          </View>
                        ))}
                      </View>
                    )}

                    {dailyReportData.discounts_breakdown?.length > 0 && (
                      <View style={{ marginBottom: 10 }}>
                        <Text style={styles.subSectionTitle}>🏷️ פילוח שוברים והנחות</Text>
                        {dailyReportData.discounts_breakdown.map((dc, idx) => (
                          <View
                            key={idx}
                            style={{
                              flexDirection: 'row-reverse',
                              justifyContent: 'space-between',
                              backgroundColor: '#0f172a',
                              padding: 8,
                              borderRadius: 8,
                              marginBottom: 4
                            }}
                          >
                            <Text style={{ color: '#e2e8f0', fontSize: 12, fontWeight: '700' }}>
                              {dc.name} ({dc.count} שוברים)
                            </Text>
                            <Text style={{ color: '#fbbf24', fontSize: 12.5, fontWeight: '800' }}>
                              ₪{Number(dc.amount_ils || 0).toFixed(2)}
                            </Text>
                          </View>
                        ))}
                      </View>
                    )}

                    {dailyReportData.hourly?.length > 0 && (
                      <View>
                        <Text style={styles.subSectionTitle}>
                          🕒 תנועות ופדיון לפי שעות ({dailyReportData.date_display || dailyReportData.report_date})
                        </Text>
                        {dailyReportData.hourly.map((h, idx) => (
                          <View
                            key={idx}
                            style={{
                              flexDirection: 'row-reverse',
                              justifyContent: 'space-between',
                              backgroundColor: '#0f172a',
                              paddingVertical: 6,
                              paddingHorizontal: 10,
                              borderRadius: 7,
                              marginBottom: 4
                            }}
                          >
                            <Text style={{ color: '#f8fafc', fontWeight: '800', fontSize: 12, width: 50, textAlign: 'right' }}>
                              {h.hour}
                            </Text>
                            <Text style={{ color: '#38bdf8', fontSize: 12 }}>⬆️ {h.entries} כנ׳</Text>
                            <Text style={{ color: '#c084fc', fontSize: 12 }}>⬇️ {h.exits} יצ׳</Text>
                            <Text style={{ color: '#34d399', fontWeight: '800', fontSize: 12, width: 70 }}>
                              ₪{Number(h.revenue_ils || 0).toFixed(1)}
                            </Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                ) : (
                  <Text style={{ color: '#94a3b8', fontSize: 12, textAlign: 'right' }}>
                    בחר תאריך מלוח השנה ולחץ "הצג" לטעינת דוח הכנסות ותנועות רכבים.
                  </Text>
                )}
              </View>
            </ScrollView>
          )}

          {/* ================= TAB 3: COMPANIES & SUBSCRIBERS ================= */}
          {activeTab === 'companies' && (
            <View style={{ flex: 1, padding: 12 }}>
              {!selectedCompany ? (
                <View style={{ flex: 1 }}>
                  <TouchableWithoutFeedback onPress={() => companySearchInputRef.current?.focus()}>
                    <View style={styles.searchBarRow}>
                      <Text style={{ fontSize: 15, marginLeft: 8 }}>🔍</Text>
                      <View style={{ flex: 1, justifyContent: 'center', position: 'relative' }}>
                        {!companySearch && !companySearchFocused && (
                          <Text
                            pointerEvents="none"
                            style={[
                              styles.companyName,
                              {
                                position: 'absolute',
                                right: 0,
                                left: 0,
                                color: '#94a3b8'
                              }
                            ]}
                          >
                            חיפוש חברה לפי שם או מספר חוזה
                          </Text>
                        )}
                        <TextInput
                          ref={companySearchInputRef}
                          style={styles.searchBarInput}
                          value={companySearch}
                          onChangeText={setCompanySearch}
                          onFocus={() => setCompanySearchFocused(true)}
                          onBlur={() => setCompanySearchFocused(false)}
                          placeholder=""
                          returnKeyType="search"
                          inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                        />
                      </View>
                      {companySearch ? (
                        <TouchableOpacity
                          onPress={() => setCompanySearch('')}
                          style={{ paddingHorizontal: 6, paddingVertical: 4 }}
                        >
                          <Text style={{ color: '#94a3b8', fontSize: 14, fontWeight: '800' }}>✕</Text>
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  </TouchableWithoutFeedback>
                  {companiesLoading ? (
                    <ActivityIndicator color="#38bdf8" size="large" style={{ marginTop: 24 }} />
                  ) : (
                    <ScrollView>
                      {companies
                        .filter(
                          (c) =>
                            !companySearch ||
                            (c.name || '').toLowerCase().includes(companySearch.toLowerCase()) ||
                            String(c.id).includes(companySearch)
                        )
                        .map((c) => (
                          <TouchableOpacity
                            key={c.id}
                            style={styles.companyRowCard}
                            onPress={() => openCompanySubscribers(c)}
                          >
                            <View>
                              <Text style={styles.companyName}>{c.name}</Text>
                              <Text style={styles.companyMeta}>חוזה #{c.id}</Text>
                            </View>
                            <View style={{ alignItems: 'flex-end' }}>
                              <Text style={{ color: '#38bdf8', fontWeight: '800', fontSize: 13 }}>
                                פתח מנויים ←
                              </Text>
                            </View>
                          </TouchableOpacity>
                        ))}
                    </ScrollView>
                  )}
                </View>
              ) : (
                <View style={{ flex: 1 }}>
                  <View style={styles.companyDetailHeader}>
                    <TouchableOpacity
                      style={styles.backBtn}
                      onPress={() => {
                        setSelectedCompany(null);
                        setSubscribers([]);
                      }}
                    >
                      <Text style={{ color: '#fff', fontWeight: '700', fontSize: 12 }}>
                        → כל החברות
                      </Text>
                    </TouchableOpacity>
                    <View style={{ flex: 1, marginHorizontal: 10 }}>
                      <Text style={styles.companyName}>{selectedCompany.name}</Text>
                      <Text style={styles.companyMeta}>
                        בפנים כעת: {selectedCompany.present_counter ?? 0} /{' '}
                        {selectedCompany.max_counter ?? 0} • מנויים: {subscribers.length}
                      </Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <TouchableOpacity
                        style={[styles.kbCheckInlineBtn, { height: 34, width: 34 }]}
                        onPress={() => Keyboard.dismiss()}
                      >
                        <Text style={[styles.kbCheckInlineText, { fontSize: 15 }]}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={styles.quotaInput}
                        value={companyQuotaInput}
                        onChangeText={setCompanyQuotaInput}
                        keyboardType="number-pad"
                        returnKeyType="done"
                        onSubmitEditing={() => Keyboard.dismiss()}
                        inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                      />
                      <TouchableOpacity style={styles.quotaSaveBtn} onPress={saveCompanyQuota}>
                        <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>
                          שמור מכסה
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>

                  <View style={{ flexDirection: 'row-reverse', gap: 8, marginBottom: 10 }}>
                    <TouchableWithoutFeedback onPress={() => subSearchInputRef.current?.focus()}>
                      <View style={[styles.searchBarRow, { flex: 1, marginBottom: 0 }]}>
                        <Text style={{ fontSize: 15, marginLeft: 8 }}>🔍</Text>
                        <View style={{ flex: 1, justifyContent: 'center', position: 'relative' }}>
                          {!subSearch && !subSearchFocused && (
                            <Text
                              pointerEvents="none"
                              style={[
                                styles.companyName,
                                {
                                  position: 'absolute',
                                  right: 0,
                                  left: 0,
                                  color: '#94a3b8'
                                }
                              ]}
                            >
                              חיפוש מנוי לפי שם או מספר רכב
                            </Text>
                          )}
                          <TextInput
                            ref={subSearchInputRef}
                            style={styles.searchBarInput}
                            value={subSearch}
                            onChangeText={setSubSearch}
                            onFocus={() => setSubSearchFocused(true)}
                            onBlur={() => setSubSearchFocused(false)}
                            placeholder=""
                            returnKeyType="search"
                            inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                          />
                        </View>
                        {subSearch ? (
                          <TouchableOpacity
                            onPress={() => setSubSearch('')}
                            style={{ paddingHorizontal: 6, paddingVertical: 4 }}
                          >
                            <Text style={{ color: '#94a3b8', fontSize: 14, fontWeight: '800' }}>✕</Text>
                          </TouchableOpacity>
                        ) : null}
                      </View>
                    </TouchableWithoutFeedback>
                    <TouchableOpacity
                      style={[
                        styles.presentFilterBtn,
                        subOnlyPresent && { backgroundColor: '#10b981', borderColor: '#10b981' }
                      ]}
                      onPress={() => setSubOnlyPresent(!subOnlyPresent)}
                    >
                      <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>
                        🟢 בחניון
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {companiesLoading ? (
                    <ActivityIndicator color="#38bdf8" size="large" style={{ marginTop: 24 }} />
                  ) : (
                    <ScrollView>
                      {subscribers
                        .filter((s) => {
                          const isPres = !!(s.present ?? s.isPresent);
                          if (subOnlyPresent && !isPres) return false;
                          if (!subSearch) return true;
                          const q = subSearch.toLowerCase();
                          const fullName = (s.full_name || s.name || '').toLowerCase();
                          return (
                            fullName.includes(q) ||
                            (s.lpn1 || '').toLowerCase().includes(q) ||
                            (s.lpn2 || '').toLowerCase().includes(q) ||
                            (s.lpn3 || '').toLowerCase().includes(q)
                          );
                        })
                        .map((s) => {
                          const isPres = !!(s.present ?? s.isPresent);
                          const fullName = s.full_name || s.name || `מנוי ${s.id}`;
                          return (
                            <View key={s.id} style={styles.subCard}>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.subName}>
                                  {fullName}{' '}
                                  <Text
                                    style={{
                                      fontSize: 11,
                                      color: isPres ? '#10b981' : '#94a3b8'
                                    }}
                                  >
                                    ({isPres ? '🟢 בחניון' : '⚪ בחוץ'})
                                  </Text>
                                </Text>
                                <Text style={styles.subMeta}>
                                  רכבים:{' '}
                                  {[s.lpn1, s.lpn2, s.lpn3].filter(Boolean).join(' , ') ||
                                    'ללא רכב'}
                                </Text>
                                <Text style={styles.subMeta}>
                                  תוקף עד: {(s.valid_until || s.validUntil || '').slice(0, 10)}
                                </Text>
                              </View>
                              <TouchableOpacity
                                style={styles.editSubBtn}
                                onPress={() =>
                                  setEditingSub({
                                    ...s,
                                    first_name: s.first_name ?? s.firstName ?? '',
                                    last_name: s.last_name ?? s.lastName ?? '',
                                    valid_from: s.valid_from ?? s.validFrom ?? '',
                                    valid_until: s.valid_until ?? s.validUntil ?? '',
                                    match_code: s.match_code ?? s.matchCode ?? '',
                                    resetPresence: false
                                  })
                                }
                              >
                                <Text style={{ color: '#38bdf8', fontWeight: '700', fontSize: 12 }}>
                                  ✏️ עדכן
                                </Text>
                              </TouchableOpacity>
                            </View>
                          );
                        })}
                    </ScrollView>
                  )}
                </View>
              )}
            </View>
          )}

          {/* ================= TAB 4: VEHICLE SEARCH (PATROL) ================= */}
          {activeTab === 'search' && (
            <ScrollView contentContainerStyle={{ padding: 14 }} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>
                  🔍 חיפוש רכב (סייר / בירור מנוי או מזדמן לתשלום)
                </Text>
                <Text style={{ color: '#94a3b8', fontSize: 12, marginBottom: 12, textAlign: 'right' }}>
                  הקלד מספר רכב כדי לבדוק מיידית האם הרכב מנוי או מזדמן שנמצא בחניון וכמה עליו לשלם כעת:
                </Text>
                <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                  <TouchableOpacity
                    style={styles.kbCheckInlineBtn}
                    onPress={() => Keyboard.dismiss()}
                  >
                    <Text style={styles.kbCheckInlineText}>✓</Text>
                  </TouchableOpacity>
                  <TextInput
                    style={[styles.textInput, styles.searchPlateBigInput, { flex: 1, marginBottom: 0 }]}
                    value={searchPlateInput}
                    onChangeText={setSearchPlateInput}
                    placeholder="12345678"
                    placeholderTextColor="#78350f"
                    keyboardType="number-pad"
                    returnKeyType="done"
                    blurOnSubmit={true}
                    onSubmitEditing={() => {
                      Keyboard.dismiss();
                      runVehicleSearch();
                    }}
                    inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                    textAlign="center"
                  />
                  <TouchableOpacity
                    style={[
                      styles.primaryBtn,
                      { width: 'auto', marginTop: 0, paddingHorizontal: 22, justifyContent: 'center' }
                    ]}
                    onPress={() => {
                      Keyboard.dismiss();
                      runVehicleSearch();
                    }}
                    disabled={searchLoading}
                  >
                    {searchLoading ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.primaryBtnText}>בדוק</Text>
                    )}
                  </TouchableOpacity>
                </View>
              </View>

              {searchResult && (
                <View style={styles.sectionCard}>
                  <View
                    style={{
                      flexDirection: 'row-reverse',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 10
                    }}
                  >
                    <View style={styles.ilPlateMini}>
                      <Text style={[styles.ilPlateMiniText, { fontSize: 18 }]}>
                        {searchResult.formatted_plate || searchResult.plate}
                      </Text>
                    </View>
                    <Text
                      style={{
                        flex: 1,
                        color: searchResult.is_subscriber
                          ? '#34d399'
                          : searchResult.ticket_payment?.found || searchResult.has_active_ticket
                          ? '#fbbf24'
                          : '#94a3b8',
                        fontWeight: '800',
                        fontSize: 14,
                        textAlign: 'left'
                      }}
                      numberOfLines={2}
                    >
                      {searchResult.is_subscriber
                        ? searchResult.vehicle?.status_title || '👤 רכב מנוי'
                        : searchResult.ticket_payment?.found || searchResult.has_active_ticket
                        ? '🎟️ רכב מזדמן בחניון'
                        : '⚪ לא נמצא כרטיס פעיל'}
                    </Text>
                  </View>

                  {/* SUBSCRIBER RESULT */}
                  {searchResult.is_subscriber && searchResult.vehicle && (
                    <View style={styles.resultBoxSub}>
                      <Text style={styles.resultBoxTitle}>👤 רכב מנוי במערכת</Text>
                      <Text style={styles.resultLine}>
                        שם מנוי: {searchResult.vehicle.subscriber_name}
                      </Text>
                      <Text style={styles.resultLine}>חברה: {searchResult.vehicle.company}</Text>
                      <Text style={styles.resultLine}>
                        תוקף: {searchResult.vehicle.valid_from} עד {searchResult.vehicle.valid_until}
                      </Text>
                      <Text style={styles.resultLine}>
                        נוכחות בחניון:{' '}
                        {searchResult.vehicle.present ? '🟢 נמצא בחניון' : '⚪ מחוץ לחניון'}
                      </Text>
                      {searchResult.vehicle.issues?.length > 0 && (
                        <Text style={[styles.resultLine, { color: '#fca5a5', fontWeight: '700' }]}>
                          ⚠️ הערות: {searchResult.vehicle.issues.join(' | ')}
                        </Text>
                      )}
                    </View>
                  )}

                  {/* TRANSIENT RESULT */}
                  {searchResult.ticket_payment?.found && (() => {
                    const tp = searchResult.ticket_payment;
                    const amt = Number(tp.amount_nis ?? tp.amount_ils ?? 0);
                    const needPay =
                      tp.payment_required !== undefined
                        ? tp.payment_required
                        : tp.paid !== undefined
                        ? !tp.paid
                        : amt > 0;
                    const durText = tp.duration || tp.stay_duration || '-';
                    const ticketId = tp.ticket_id || tp.epan || '';
                    return (
                      <View style={styles.resultBoxTrans}>
                        <Text style={[styles.resultBoxTitle, { color: '#fbbf24', textAlign: 'right' }]}>
                          🎟️ כרטיס חניה מזדמן פעיל בחניון — תחשיב תשלום
                        </Text>
                        {ticketId ? (
                          <Text style={styles.resultLine}>מזהה כרטיס: {ticketId}</Text>
                        ) : null}
                        <Text style={styles.resultLine}>
                          שעת כניסה: {tp.entry_time || '-'}
                        </Text>
                        <Text style={styles.resultLine}>
                          זמן שהייה: {durText} • נתיב כניסה #{tp.entry_device || '-'}
                        </Text>
                        <View style={styles.priceBanner}>
                          <Text
                            style={[
                              styles.priceBannerLabel,
                              { color: needPay || amt > 0 ? '#fbbf24' : '#34d399' }
                            ]}
                          >
                            {needPay || amt > 0 ? '💳 סכום לתשלום:' : '✅ ללא חיוב לתשלום (₪0)'}
                          </Text>
                          <Text style={styles.priceBannerValue}>
                            {tp.price_display || `₪${amt.toFixed(2)}`}
                          </Text>
                        </View>
                      </View>
                    );
                  })()}

                  {!searchResult.is_subscriber && !searchResult.ticket_payment?.found && (
                    <View style={{ padding: 14, alignItems: 'center' }}>
                      <Text style={{ color: '#94a3b8', textAlign: 'center' }}>
                        הרכב אינו רשום כמנוי ולא נמצא עבורו כרטיס חניה מזדמן פעיל בחניון.
                      </Text>
                      {searchResult.ticket_payment?.similar_plates?.length > 0 && (
                        <View style={{ marginTop: 12, width: '100%' }}>
                          <Text
                            style={{
                              color: '#cbd5e1',
                              fontSize: 12,
                              marginBottom: 6,
                              textAlign: 'right'
                            }}
                          >
                            לוחיות דומות שזוהו בחניון:
                          </Text>
                          <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 8 }}>
                            {searchResult.ticket_payment.similar_plates.map((sp) => {
                              const pStr = typeof sp === 'string' ? sp : sp.lpn;
                              return (
                                <TouchableOpacity
                                  key={pStr}
                                  style={styles.similarPlateBtn}
                                  onPress={() => runVehicleSearch(pStr)}
                                >
                                  <Text style={{ color: '#38bdf8', fontWeight: '700' }}>{pStr}</Text>
                                </TouchableOpacity>
                              );
                            })}
                          </View>
                        </View>
                      )}
                    </View>
                  )}
                </View>
              )}
            </ScrollView>
          )}
        </View>

        {/* FOOTER: VERSION & COPYRIGHT HINT LTD */}
        <View
          style={{
            backgroundColor: '#0f172a',
            borderTopWidth: 1,
            borderTopColor: '#1e293b',
            paddingVertical: 4,
            paddingHorizontal: 10,
            alignItems: 'center'
          }}
        >
          <Text style={{ color: '#94a3b8', fontSize: 10.5, fontWeight: '700', textAlign: 'center' }}>
            © 2026 {COPYRIGHT_HOLDER} — כל הזכויות שמורות | גרסה {APP_VERSION} • שיידט את בכמן ישראל בע"מ
          </Text>
        </View>

        {/* BOTTOM NAVIGATION TABS */}
        <View style={styles.bottomTabs}>
          {[
            { key: 'ops', icon: '🚧', label: 'תפעול ונתיבים' },
            { key: 'counters', icon: '📊', label: 'נתוני חניון' },
            { key: 'companies', icon: '🏢', label: 'חברות ומנויים' },
            { key: 'search', icon: '🔍', label: 'חיפוש רכב' }
          ].map((t) => (
            <TouchableOpacity
              key={t.key}
              style={[styles.tabItem, activeTab === t.key && styles.tabItemActive]}
              onPress={() => {
                setActiveTab(t.key);
                if (t.key === 'counters') loadCounters();
                if (t.key === 'companies') loadCompanies();
              }}
            >
              <Text style={{ fontSize: 18 }}>{t.icon}</Text>
              <Text
                style={[
                  styles.tabLabel,
                  activeTab === t.key && { color: '#38bdf8', fontWeight: '800' }
                ]}
              >
                {t.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* PORTRAIT MODAL FOR SINGLE LANE LPR INSPECTOR */}
        <Modal
          visible={!isSplitLayout && !!selectedUnit && activeTab === 'ops'}
          animationType="slide"
          onRequestClose={() => setSelectedUnit(null)}
        >
          <SafeAreaView style={styles.safeArea}>{renderLaneInspector()}</SafeAreaView>
        </Modal>

        {/* MODAL: MULTI-PARKING SWITCHER */}
        <Modal
          visible={parkingChoiceModal}
          transparent
          animationType="fade"
          onRequestClose={() => setParkingChoiceModal(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalBox}>
              <Text style={styles.modalTitle}>🏢 בחירת חניון פעיל לתפעול</Text>
              {parkingOptions.map((p) => (
                <TouchableOpacity
                  key={p.project_number}
                  style={[
                    styles.parkingChoiceBtn,
                    String(userProfile?.project_number) === String(p.project_number) &&
                      styles.parkingChoiceBtnActive
                  ]}
                  onPress={() => handleSwitchParking(p.project_number)}
                >
                  <View>
                    <Text style={styles.parkingChoiceName}>
                      {p.parking_name || p.project_name || `חניון ${p.project_number}`}
                    </Text>
                    <Text style={styles.parkingChoiceMeta}>חניון #{p.project_number}</Text>
                  </View>
                  <Text style={{ color: '#38bdf8', fontWeight: '700' }}>
                    {String(userProfile?.project_number) === String(p.project_number)
                      ? 'פעיל כעת ✓'
                      : 'עבור לחניון'}
                  </Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity
                style={styles.secondaryBtn}
                onPress={() => setParkingChoiceModal(false)}
              >
                <Text style={styles.secondaryBtnText}>סגור</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {/* MODAL: UNIT SELECTION FILTER BY FACILITY */}
        <Modal
          visible={unitSelectorModal}
          transparent
          animationType="slide"
          onRequestClose={() => setUnitSelectorModal(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalBox, { maxHeight: '86%', width: '94%' }]}>
              <Text style={styles.modalTitle}>☑️ בחירת יחידות לתצוגה במסך תפעול</Text>
              <Text style={{ color: '#94a3b8', fontSize: 12, textAlign: 'right', marginBottom: 10 }}>
                סמן את היחידות או החניונים שתרצה לראות במסך התפעול (או לחץ "הצג הכל"):
              </Text>

              <View style={{ flexDirection: 'row-reverse', gap: 8, marginBottom: 10 }}>
                <TouchableOpacity
                  style={{
                    flex: 1,
                    backgroundColor: '#0284c7',
                    borderRadius: 10,
                    paddingVertical: 8,
                    alignItems: 'center'
                  }}
                  onPress={clearUnitSelectionFilter}
                >
                  <Text style={{ color: '#fff', fontWeight: '800', fontSize: 12.5 }}>
                    ✓ הצג את כל היחידות ({lanes.length})
                  </Text>
                </TouchableOpacity>
              </View>

              <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ paddingBottom: 10 }}>
                {(() => {
                  const facMap = [];
                  const facLookup = {};
                  lanes.forEach((l) => {
                    const fKey = String(l.facility_number || '3050');
                    if (!facLookup[fKey]) {
                      facLookup[fKey] = {
                        facility_number: fKey,
                        facility_name: l.facility_name || `חניון #${fKey}`,
                        items: []
                      };
                      facMap.push(facLookup[fKey]);
                    }
                    facLookup[fKey].items.push(l);
                  });

                  const activeKeys = Object.keys(selectedUnitsMap).filter((k) => selectedUnitsMap[k]);
                  const allVisibleByDefault = activeKeys.length === 0;

                  return facMap.map((fg) => (
                    <View
                      key={fg.facility_number}
                      style={{
                        backgroundColor: '#0f172a',
                        borderRadius: 12,
                        padding: 10,
                        marginBottom: 10,
                        borderWidth: 1,
                        borderColor: '#334155'
                      }}
                    >
                      <View
                        style={{
                          flexDirection: 'row-reverse',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: 8
                        }}
                      >
                        <Text style={{ color: '#38bdf8', fontWeight: '900', fontSize: 13.5, textAlign: 'right' }}>
                          🅿️ {fg.facility_name} (#{fg.facility_number})
                        </Text>
                        <TouchableOpacity
                          style={{
                            backgroundColor: '#1e293b',
                            borderWidth: 1,
                            borderColor: '#38bdf8',
                            borderRadius: 8,
                            paddingHorizontal: 10,
                            paddingVertical: 4
                          }}
                          onPress={() => selectFacilityUnitsOnly(fg.facility_number)}
                        >
                          <Text style={{ color: '#38bdf8', fontSize: 11, fontWeight: '800' }}>
                            בחר חניון זה בלבד
                          </Text>
                        </TouchableOpacity>
                      </View>

                      <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', gap: 6 }}>
                        {fg.items.map((l) => {
                          const uKey = String(l.number || l.unit);
                          const isChecked = allVisibleByDefault ? false : !!selectedUnitsMap[uKey];
                          const isEntry = l.type === 'entry';
                          const isExit = l.type === 'exit';
                          return (
                            <TouchableOpacity
                              key={uKey}
                              style={{
                                width: '48%',
                                flexDirection: 'row-reverse',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                backgroundColor: isChecked ? 'rgba(16,185,129,0.18)' : '#1e293b',
                                borderWidth: 1.5,
                                borderColor: isChecked ? '#10b981' : '#334155',
                                borderRadius: 10,
                                paddingVertical: 8,
                                paddingHorizontal: 10
                              }}
                              onPress={() => toggleUnitInSelection(uKey)}
                            >
                              <View style={{ flex: 1 }}>
                                <Text
                                  style={{
                                    color: '#f8fafc',
                                    fontWeight: '800',
                                    fontSize: 12.5,
                                    textAlign: 'right'
                                  }}
                                  numberOfLines={1}
                                >
                                  {isEntry ? '🟢' : isExit ? '🔴' : '🟡'} {l.name || `יחידה ${uKey}`}
                                </Text>
                                <Text style={{ color: '#94a3b8', fontSize: 10.5, textAlign: 'right' }}>
                                  יחידה #{uKey} • {l.type_label_he || (isEntry ? 'כניסה' : isExit ? 'יציאה' : 'מעבר')}
                                </Text>
                              </View>
                              <Text style={{ fontSize: 16, marginRight: 6 }}>
                                {isChecked ? '☑️' : '⬜'}
                              </Text>
                            </TouchableOpacity>
                          );
                        })}
                      </View>
                    </View>
                  ));
                })()}
              </ScrollView>

              <TouchableOpacity
                style={[styles.primaryBtn, { marginTop: 8 }]}
                onPress={() => setUnitSelectorModal(false)}
              >
                <Text style={styles.primaryBtnText}>
                  ✓ סיום והצג יחידות ({Object.keys(selectedUnitsMap).filter((k) => selectedUnitsMap[k]).length || 'הכל'})
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {/* MODAL: EXIT UNIT (2XX) CHECK & SEND PRICE TO DISPLAY */}
        <Modal
          visible={!!priceModalLane}
          transparent
          animationType="fade"
          onRequestClose={() => setPriceModalLane(null)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalBox, { maxWidth: 400 }]}>
              <Text style={styles.modalTitle}>
                💳 שליחת מחיר לצג יחידת יציאה #{priceModalLane?.number || priceModalLane?.unit}
              </Text>
              <Text style={{ color: '#94a3b8', fontSize: 12, textAlign: 'right', marginBottom: 10 }}>
                {priceModalLane?.name || ''} • בדיקת מחיר על הצג ושליחת סכום לתשלום (מחיר מלא + הנחה):
              </Text>

              <View
                style={{
                  backgroundColor: '#0f172a',
                  borderRadius: 11,
                  borderWidth: 1,
                  borderColor: '#334155',
                  padding: 12,
                  marginBottom: 12
                }}
              >
                <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ color: '#cbd5e1', fontSize: 12.5, fontWeight: '700' }}>
                    מחיר מוצג כעת על צג היחידה:
                  </Text>
                  <TouchableOpacity
                    style={{
                      backgroundColor: '#1e293b',
                      borderWidth: 1,
                      borderColor: '#475569',
                      borderRadius: 7,
                      paddingHorizontal: 10,
                      paddingVertical: 4
                    }}
                    onPress={() =>
                      checkExitScreenPrice(
                        priceModalLane?.number || priceModalLane?.unit,
                        priceModalLane?.cell_number || '1'
                      )
                    }
                    disabled={screenPriceLoading}
                  >
                    <Text style={{ color: '#38bdf8', fontSize: 11.5, fontWeight: '800' }}>
                      {screenPriceLoading ? 'בודק...' : '🔄 בדוק צג'}
                    </Text>
                  </TouchableOpacity>
                </View>
                <Text
                  style={{
                    color: screenPriceInfo?.active ? '#34d399' : '#94a3b8',
                    fontSize: 18,
                    fontWeight: '900',
                    textAlign: 'right',
                    marginTop: 6
                  }}
                >
                  {screenPriceLoading
                    ? '⏳ בודק מול יחידת היציאה...'
                    : screenPriceInfo?.active
                    ? `מוצג לתשלום: ${screenPriceInfo.price_display}`
                    : 'אין חיוב פעיל על הצג כרגע'}
                </Text>
              </View>

              <Text style={styles.inputLabel}>סכום לתשלום לשליחה לצג (בש"ח):</Text>
              <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 12 }}>
                <TouchableOpacity
                  style={styles.kbCheckInlineBtn}
                  onPress={() => Keyboard.dismiss()}
                >
                  <Text style={styles.kbCheckInlineText}>✓</Text>
                </TouchableOpacity>
                <TextInput
                  style={[
                    styles.textInput,
                    {
                      flex: 1,
                      marginBottom: 0,
                      height: 46,
                      fontSize: 20,
                      fontWeight: '900',
                      color: '#f8fafc',
                      backgroundColor: '#0f172a',
                      borderColor: '#38bdf8'
                    }
                  ]}
                  value={exitPriceInput}
                  onChangeText={setExitPriceInput}
                  placeholder="הקלד סכום (למשל 25)"
                  placeholderTextColor="#64748b"
                  keyboardType="numeric"
                  returnKeyType="done"
                  inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                  textAlign="center"
                />
              </View>

              <TouchableOpacity
                style={[styles.primaryBtn, { marginTop: 0 }]}
                onPress={() => sendPriceToExitUnit(priceModalLane, exitPriceInput)}
                disabled={actionBusy}
              >
                <Text style={styles.primaryBtnText}>
                  {actionBusy ? '⏳ שולח מחיר לצג היחידה...' : '💳 שלח מחיר לצג יחידת היציאה'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.secondaryBtn}
                onPress={() => setPriceModalLane(null)}
              >
                <Text style={styles.secondaryBtnText}>סגור</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {/* MODAL: EDIT COUNTER MAX PLACES */}
        <Modal
          visible={!!counterEditModal}
          transparent
          animationType="fade"
          onRequestClose={() => setCounterEditModal(null)}
        >
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          >
            <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
              <View style={styles.modalBackdrop}>
                <View style={styles.modalBox}>
                  <Text style={styles.modalTitle}>✏️ עדכון תקרת מקומות ({counterEditModal?.name})</Text>
                  <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                    <TouchableOpacity
                      style={styles.kbCheckInlineBtn}
                      onPress={() => Keyboard.dismiss()}
                    >
                      <Text style={styles.kbCheckInlineText}>✓</Text>
                    </TouchableOpacity>
                    <TextInput
                      style={[styles.textInput, { flex: 1, marginBottom: 0 }]}
                      value={counterEditValue}
                      onChangeText={setCounterEditValue}
                      keyboardType="number-pad"
                      returnKeyType="done"
                      onSubmitEditing={() => Keyboard.dismiss()}
                      textAlign="center"
                    />
                  </View>
                  <TouchableOpacity
                    style={styles.primaryBtn}
                    onPress={() => {
                      Keyboard.dismiss();
                      updateCounterAction(
                        counterEditModal.facilityId,
                        counterEditModal.counterId,
                        'maxplaces',
                        parseInt(counterEditValue || '0', 10)
                      );
                    }}
                  >
                    <Text style={styles.primaryBtnText}>שמור תקרה חדשה</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.secondaryBtn}
                    onPress={() => setCounterEditModal(null)}
                  >
                    <Text style={styles.secondaryBtnText}>ביטול</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </TouchableWithoutFeedback>
          </KeyboardAvoidingView>
        </Modal>

        {/* MODAL: EDIT SUBSCRIBER */}
        <Modal
          visible={!!editingSub}
          transparent
          animationType="slide"
          onRequestClose={() => setEditingSub(null)}
        >
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          >
            <View style={styles.modalBackdrop}>
              <ScrollView
                style={{ width: '100%' }}
                contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 14 }}
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="interactive"
              >
                {editingSub && (
                  <View style={[styles.modalBox, { width: '100%', maxWidth: 440 }]}>
                    {/* TOP STICKY HEADER WITH SAVE, KEYBOARD DISMISS, AND CANCEL */}
                    <View
                      style={{
                        flexDirection: 'row-reverse',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 12,
                        paddingBottom: 10,
                        borderBottomWidth: 1,
                        borderBottomColor: '#334155',
                        gap: 8
                      }}
                    >
                      <Text style={[styles.modalTitle, { marginBottom: 0, flex: 1 }]}>
                        ✏️ עדכון מנוי #{editingSub.id}
                      </Text>
                      <TouchableOpacity
                        style={{
                          backgroundColor: '#10b981',
                          paddingHorizontal: 14,
                          paddingVertical: 8,
                          borderRadius: 10,
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 5
                        }}
                        onPress={saveSubscriberEdit}
                        disabled={savingSubLoading}
                      >
                        {savingSubLoading ? (
                          <ActivityIndicator color="#fff" size="small" />
                        ) : (
                          <Text style={{ color: '#fff', fontWeight: '900', fontSize: 13.5 }}>
                            ✓ אישור ושמירה
                          </Text>
                        )}
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={{
                          backgroundColor: '#334155',
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                          borderRadius: 10
                        }}
                        onPress={() => {
                          Keyboard.dismiss();
                          setEditingSub(null);
                        }}
                      >
                        <Text style={{ color: '#cbd5e1', fontWeight: '800', fontSize: 13 }}>✕</Text>
                      </TouchableOpacity>
                    </View>

                    <Text style={styles.inputLabel}>שם משפחה</Text>
                    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                      <TouchableOpacity
                        style={styles.kbCheckInlineBtn}
                        onPress={() => Keyboard.dismiss()}
                      >
                        <Text style={styles.kbCheckInlineText}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={[styles.textInput, { flex: 1, marginBottom: 0, textAlign: 'right' }]}
                        value={editingSub.last_name}
                        onChangeText={(v) => setEditingSub({ ...editingSub, last_name: v })}
                        returnKeyType="done"
                        blurOnSubmit={true}
                        onSubmitEditing={() => Keyboard.dismiss()}
                      />
                    </View>

                    <Text style={styles.inputLabel}>שם פרטי</Text>
                    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                      <TouchableOpacity
                        style={styles.kbCheckInlineBtn}
                        onPress={() => Keyboard.dismiss()}
                      >
                        <Text style={styles.kbCheckInlineText}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={[styles.textInput, { flex: 1, marginBottom: 0, textAlign: 'right' }]}
                        value={editingSub.first_name}
                        onChangeText={(v) => setEditingSub({ ...editingSub, first_name: v })}
                        returnKeyType="done"
                        blurOnSubmit={true}
                        onSubmitEditing={() => Keyboard.dismiss()}
                      />
                    </View>

                    <Text style={styles.inputLabel}>מספר רכב 1 (ראשי) — לחץ ✓ לאישור</Text>
                    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                      <TouchableOpacity
                        style={[styles.kbCheckInlineBtn, { backgroundColor: '#10b981', borderColor: '#059669' }]}
                        onPress={saveSubscriberEdit}
                        disabled={savingSubLoading}
                      >
                        <Text style={styles.kbCheckInlineText}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={[styles.textInput, { flex: 1, marginBottom: 0, textAlign: 'center', fontWeight: '800', fontSize: 17 }]}
                        value={editingSub.lpn1}
                        onChangeText={(v) => setEditingSub({ ...editingSub, lpn1: v })}
                        keyboardType="numbers-and-punctuation"
                        returnKeyType="done"
                        blurOnSubmit={true}
                        onSubmitEditing={() => Keyboard.dismiss()}
                      />
                    </View>

                    <Text style={styles.inputLabel}>מספר רכב 2</Text>
                    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                      <TouchableOpacity
                        style={[styles.kbCheckInlineBtn, { backgroundColor: '#10b981', borderColor: '#059669' }]}
                        onPress={saveSubscriberEdit}
                        disabled={savingSubLoading}
                      >
                        <Text style={styles.kbCheckInlineText}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={[styles.textInput, { flex: 1, marginBottom: 0, textAlign: 'center', fontWeight: '800', fontSize: 17 }]}
                        value={editingSub.lpn2}
                        onChangeText={(v) => setEditingSub({ ...editingSub, lpn2: v })}
                        keyboardType="numbers-and-punctuation"
                        returnKeyType="done"
                        blurOnSubmit={true}
                        onSubmitEditing={() => Keyboard.dismiss()}
                      />
                    </View>

                    <Text style={styles.inputLabel}>מספר רכב 3</Text>
                    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 12 }}>
                      <TouchableOpacity
                        style={[styles.kbCheckInlineBtn, { backgroundColor: '#10b981', borderColor: '#059669' }]}
                        onPress={saveSubscriberEdit}
                        disabled={savingSubLoading}
                      >
                        <Text style={styles.kbCheckInlineText}>✓</Text>
                      </TouchableOpacity>
                      <TextInput
                        style={[styles.textInput, { flex: 1, marginBottom: 0, textAlign: 'center', fontWeight: '800', fontSize: 17 }]}
                        value={editingSub.lpn3}
                        onChangeText={(v) => setEditingSub({ ...editingSub, lpn3: v })}
                        keyboardType="numbers-and-punctuation"
                        returnKeyType="done"
                        blurOnSubmit={true}
                        onSubmitEditing={() => Keyboard.dismiss()}
                      />
                    </View>

                    <View
                      style={[
                        styles.switchRow,
                        {
                          backgroundColor: 'rgba(245,158,11,0.12)',
                          borderWidth: 1,
                          borderColor: 'rgba(245,158,11,0.35)',
                          borderRadius: 10,
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                          marginBottom: 8
                        }
                      ]}
                    >
                      <Switch
                        value={!!editingSub.resetPresence}
                        onValueChange={(v) => setEditingSub({ ...editingSub, resetPresence: v })}
                      />
                      <Text style={{ flex: 1, color: '#fbbf24', fontSize: 13, fontWeight: '700', textAlign: 'right' }}>
                        אפס נוכחות בחניון (שחרור כניסה כפולה)
                      </Text>
                    </View>

                    <TouchableOpacity
                      style={[styles.primaryBtn, savingSubLoading && { opacity: 0.7 }]}
                      onPress={saveSubscriberEdit}
                      disabled={savingSubLoading}
                    >
                      {savingSubLoading ? (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <ActivityIndicator color="#fff" size="small" />
                          <Text style={styles.primaryBtnText}>שומר שינויים בחניון...</Text>
                        </View>
                      ) : (
                        <Text style={styles.primaryBtnText}>💾 שמור שינויים ורשום באירועים</Text>
                      )}
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.secondaryBtn}
                      onPress={() => {
                        Keyboard.dismiss();
                        setEditingSub(null);
                      }}
                    >
                      <Text style={styles.secondaryBtnText}>ביטול</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </ScrollView>
            </View>
          </KeyboardAvoidingView>
        </Modal>

        {/* MODAL: INTERACTIVE CALENDAR DATE PICKER */}
        <Modal
          visible={!!calendarModalTarget}
          transparent
          animationType="fade"
          onRequestClose={() => setCalendarModalTarget(null)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalBox, { maxWidth: 380, padding: 16 }]}>
              <Text style={styles.modalTitle}>
                📅 {calendarModalTarget === 'end' ? 'בחירת תאריך סיום' : isDateRangeMode ? 'בחירת תאריך התחלה' : 'בחירת תאריך לדוח'}
              </Text>

              {/* Month & Year Navigation */}
              {(() => {
                const heMonths = [
                  'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
                  'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'
                ];
                const heDays = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳'];
                const daysInMonth = new Date(calendarViewYear, calendarViewMonth + 1, 0).getDate();
                const firstWeekday = new Date(calendarViewYear, calendarViewMonth, 1).getDay(); // 0=Sunday
                const cells = [];
                for (let i = 0; i < firstWeekday; i++) {
                  cells.push(null);
                }
                for (let d = 1; d <= daysInMonth; d++) {
                  cells.push(d);
                }
                const activeDateStr = calendarModalTarget === 'end' ? reportEndDateInput : reportDateInput;

                return (
                  <View style={{ width: '100%' }}>
                    <View
                      style={{
                        flexDirection: 'row-reverse',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 12,
                        backgroundColor: '#0f172a',
                        padding: 8,
                        borderRadius: 10
                      }}
                    >
                      <TouchableOpacity
                        style={{ paddingHorizontal: 12, paddingVertical: 6, backgroundColor: '#1e293b', borderRadius: 8 }}
                        onPress={() => {
                          if (calendarViewMonth === 0) {
                            setCalendarViewMonth(11);
                            setCalendarViewYear(calendarViewYear - 1);
                          } else {
                            setCalendarViewMonth(calendarViewMonth - 1);
                          }
                        }}
                      >
                        <Text style={{ color: '#38bdf8', fontWeight: '800', fontSize: 13 }}>▶ חודש קודם</Text>
                      </TouchableOpacity>

                      <Text style={{ color: '#f8fafc', fontSize: 16, fontWeight: '900' }}>
                        {heMonths[calendarViewMonth]} {calendarViewYear}
                      </Text>

                      <TouchableOpacity
                        style={{ paddingHorizontal: 12, paddingVertical: 6, backgroundColor: '#1e293b', borderRadius: 8 }}
                        onPress={() => {
                          if (calendarViewMonth === 11) {
                            setCalendarViewMonth(0);
                            setCalendarViewYear(calendarViewYear + 1);
                          } else {
                            setCalendarViewMonth(calendarViewMonth + 1);
                          }
                        }}
                      >
                        <Text style={{ color: '#38bdf8', fontWeight: '800', fontSize: 13 }}>חודש הבא ◀</Text>
                      </TouchableOpacity>
                    </View>

                    {/* Day of Week Headers (Right-to-Left: Sunday to Saturday) */}
                    <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-around', marginBottom: 6 }}>
                      {heDays.map((dLbl, i) => (
                        <Text
                          key={i}
                          style={{
                            width: '13.5%',
                            textAlign: 'center',
                            color: '#94a3b8',
                            fontWeight: '800',
                            fontSize: 12
                          }}
                        >
                          {dLbl}
                        </Text>
                      ))}
                    </View>

                    {/* Calendar Days Grid */}
                    <View style={{ flexDirection: 'row-reverse', flexWrap: 'wrap', justifyContent: 'flex-start' }}>
                      {cells.map((dayNum, idx) => {
                        if (!dayNum) {
                          return <View key={`empty_${idx}`} style={{ width: '14.28%', height: 40 }} />;
                        }
                        const isoStr = `${calendarViewYear}-${String(calendarViewMonth + 1).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
                        const isSelected = isoStr === activeDateStr;
                        const isInRange =
                          isDateRangeMode &&
                          isoStr >= reportDateInput &&
                          isoStr <= reportEndDateInput;

                        return (
                          <TouchableOpacity
                            key={isoStr}
                            style={{
                              width: '14.28%',
                              height: 40,
                              justifyContent: 'center',
                              alignItems: 'center',
                              borderRadius: 9,
                              marginVertical: 2,
                              backgroundColor: isSelected
                                ? '#0284c7'
                                : isInRange
                                ? 'rgba(56,189,248,0.18)'
                                : 'transparent',
                              borderWidth: isSelected ? 1.5 : 0,
                              borderColor: '#38bdf8'
                            }}
                            onPress={() => handleCalendarDayPick(dayNum)}
                          >
                            <Text
                              style={{
                                color: isSelected ? '#fff' : isInRange ? '#38bdf8' : '#e2e8f0',
                                fontWeight: isSelected || isInRange ? '900' : '600',
                                fontSize: 14
                              }}
                            >
                              {dayNum}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  </View>
                );
              })()}

              <TouchableOpacity
                style={[styles.secondaryBtn, { marginTop: 14 }]}
                onPress={() => setCalendarModalTarget(null)}
              >
                <Text style={styles.secondaryBtnText}>סגור לוח שנה</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {Platform.OS === 'ios' && (
          <InputAccessoryView nativeID={KB_ACCESSORY_ID}>
            <View style={styles.kbAccessoryBar}>
              <View />
              <TouchableOpacity
                style={styles.kbAccessoryDoneBtn}
                onPress={() => Keyboard.dismiss()}
              >
                <Text style={styles.kbAccessoryDoneText}>✓ אישור והורד מקלדת</Text>
              </TouchableOpacity>
            </View>
          </InputAccessoryView>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );

  // =====================================================
  // HELPER RENDER: SINGLE LANE INSPECTOR + CONTROLS (CLEAN COLORS, COMPACT LPR, EXIT PRICE SENDER)
  // =====================================================
  function renderLaneInspector() {
    const lane =
      lanes.find((l) => String(l.number || l.unit) === String(selectedUnit)) || {
        number: selectedUnit,
        name: `נתיב ${selectedUnit}`
      };
    const vInfo = laneDetail?.vehicle;
    const displayPlate =
      laneDetail?.formatted_plate ||
      laneDetail?.plate ||
      lane.formatted_plate ||
      lane.last_plate ||
      '';
    const rawPlateClean = String(laneDetail?.plate || lane.last_plate || displayPlate).replace(/[^0-9A-Za-z]/g, '');
    const unitNumInt = parseInt(String(selectedUnit), 10) || 0;
    const isExitUnit = lane.direction === 'exit' || (unitNumInt >= 200 && unitNumInt <= 299);

    return (
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: 14,
          paddingTop: !isSplitLayout && Platform.OS === 'ios' ? 44 : 14,
          paddingBottom: 28
        }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.inspectorHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.inspectorTitle}>
              {lane.name || `נתיב ${selectedUnit}`} (#{selectedUnit})
            </Text>
            <Text style={{ color: '#94a3b8', fontSize: 11.5, textAlign: 'right' }}>
              {lane.device_state_label || lane.type_label_he || ''}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={() => {
                selectLane(selectedUnit);
                loadOverview(true, null, true);
              }}
            >
              <Text style={{ fontSize: 16 }}>🔄</Text>
            </TouchableOpacity>
            {!isSplitLayout && (
              <TouchableOpacity
                style={[styles.backBtn, { backgroundColor: '#334155', borderWidth: 1, borderColor: '#475569', paddingHorizontal: 14, paddingVertical: 9 }]}
                onPress={() => setSelectedUnit(null)}
              >
                <Text style={{ color: '#f8fafc', fontWeight: '800', fontSize: 13 }}>✕ יציאה מנתיב</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Last Detected License Plate Card (Clean Slate Border) */}
        <View
          style={{
            backgroundColor: '#1e293b',
            borderRadius: 14,
            borderWidth: 1,
            borderColor: '#334155',
            padding: 12,
            marginBottom: 10,
            alignItems: 'center'
          }}
        >
          <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: '700', marginBottom: 6 }}>
            {laneDetailLoading ? '⏳ בודק רכב אחרון בנתיב...' : '🚗 רכב אחרון שנקרא בנתיב:'}
          </Text>
          {displayPlate ? (
            <TouchableOpacity
              activeOpacity={0.85}
              onPress={() => {
                setFixPlateText(rawPlateClean);
                setFixPlateFirstTapClear(true);
              }}
              style={[styles.ilPlateMini, { paddingHorizontal: 18, paddingVertical: 5 }]}
            >
              <Text style={[styles.ilPlateMiniText, { fontSize: 21 }]}>{displayPlate}</Text>
            </TouchableOpacity>
          ) : laneDetailLoading ? (
            <ActivityIndicator color="#38bdf8" size="small" style={{ marginVertical: 6 }} />
          ) : (
            <Text style={{ color: '#64748b', fontSize: 13.5, fontWeight: '700', marginVertical: 4 }}>
              לא נמצאה קריאת רכב אחרונה בנתיב
            </Text>
          )}
          {laneDetail?.event_time ? (
            <Text style={{ color: '#94a3b8', fontSize: 11, marginTop: 5 }}>
              זמן זיהוי: {laneDetail.event_time}
            </Text>
          ) : null}
        </View>

        {/* Vehicle Classification in Lane */}
        {vInfo && displayPlate ? (
          <View style={styles.laneVehicleBox}>
            <Text style={{ color: '#e2e8f0', fontWeight: '800', fontSize: 13, textAlign: 'right' }}>
              סטטוס רכב: {vInfo.status_title}
            </Text>
            {vInfo.is_subscriber && (
              <Text style={{ color: '#cbd5e1', fontSize: 12, marginTop: 3, textAlign: 'right' }}>
                👤 {vInfo.subscriber_name} • {vInfo.company}
              </Text>
            )}
            {vInfo.price_info?.found && (
              <Text style={{ color: '#38bdf8', fontSize: 12, fontWeight: '700', marginTop: 3, textAlign: 'right' }}>
                🎟️ מזדמן לתשלום: {vInfo.price_info.price_display} (שהייה: {vInfo.price_info.stay_duration || vInfo.price_info.duration || '-'})
              </Text>
            )}
          </View>
        ) : null}

        {/* 6 Barrier & Device Control Buttons (Restrained Professional Palette) */}
        <Text style={styles.subSectionTitle}>שליטה במחסום ונעילת נתיב</Text>
        <View style={styles.cmdGrid}>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#059669' }]}
            onPress={() => sendLaneCommand(lane, 'OPEN', 'פתיחת מחסום')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>🔼 פתח מחסום</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#334155', borderWidth: 1, borderColor: '#475569' }]}
            onPress={() => sendLaneCommand(lane, 'CLOSE', 'סגירת מחסום')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>🔽 סגור מחסום</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#991b1b' }]}
            onPress={() => sendLaneCommand(lane, 'LOCK_BARRIER', 'נעילת מחסום')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>🔒 נעל מחסום</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#475569' }]}
            onPress={() => sendLaneCommand(lane, 'UNLOCK_BARRIER', 'שחרור נעילת מחסום')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>🔓 שחרר נעילה</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#7f1d1d' }]}
            onPress={() => sendLaneCommand(lane, 'BLOCK_DEVICE', 'חסימת מסוף')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>⛔ חסום מסוף</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.cmdBtn, { backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#475569' }]}
            onPress={() => sendLaneCommand(lane, 'UNBLOCK_DEVICE', 'שחרור חסימת מסוף')}
            disabled={actionBusy}
          >
            <Text style={styles.cmdBtnText}>✅ שחרר מסוף</Text>
          </TouchableOpacity>
        </View>

        {/* EXIT LANE (2XX) SCREEN PRICE CHECK & 2-STEP SEND PRICE */}
        {isExitUnit && (
          <View style={[styles.fixPlateCard, { marginBottom: 10 }]}>
            <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <Text style={[styles.subSectionTitle, { marginBottom: 0 }]}>
                💳 מחיר על צג היציאה ושליחת חיוב
              </Text>
              <TouchableOpacity
                style={{
                  backgroundColor: '#0f172a',
                  borderWidth: 1,
                  borderColor: '#475569',
                  borderRadius: 8,
                  paddingHorizontal: 10,
                  paddingVertical: 4
                }}
                onPress={() => checkExitScreenPrice(selectedUnit, lane.cell_number || '1')}
                disabled={screenPriceLoading}
              >
                <Text style={{ color: '#38bdf8', fontSize: 11.5, fontWeight: '800' }}>
                  {screenPriceLoading ? 'בודק...' : '🔄 בדוק צג'}
                </Text>
              </TouchableOpacity>
            </View>

            <View
              style={{
                backgroundColor: '#0f172a',
                borderRadius: 9,
                paddingVertical: 7,
                paddingHorizontal: 10,
                marginBottom: 8,
                borderWidth: 1,
                borderColor: '#334155',
                flexDirection: 'row-reverse',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: '700' }}>
                מוצג כעת על צג יחידה #{selectedUnit}:
              </Text>
              <Text
                style={{
                  color: screenPriceInfo?.active ? '#34d399' : '#cbd5e1',
                  fontSize: 14,
                  fontWeight: '900'
                }}
              >
                {screenPriceLoading
                  ? 'בודק...'
                  : screenPriceInfo?.active
                  ? screenPriceInfo.price_display
                  : 'אין מחיר על הצג'}
              </Text>
            </View>

            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
              <TouchableOpacity
                style={styles.kbCheckInlineBtn}
                onPress={() => Keyboard.dismiss()}
              >
                <Text style={styles.kbCheckInlineText}>✓</Text>
              </TouchableOpacity>
              <TextInput
                style={[
                  styles.textInput,
                  {
                    flex: 1,
                    marginBottom: 0,
                    height: 44,
                    backgroundColor: '#0f172a',
                    borderColor: '#475569',
                    color: '#f8fafc',
                    fontSize: 17,
                    fontWeight: '800'
                  }
                ]}
                value={exitPriceInput}
                onChangeText={setExitPriceInput}
                placeholder='סכום בש"ח (למשל 25)'
                placeholderTextColor="#64748b"
                keyboardType="numeric"
                returnKeyType="done"
                inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                textAlign="center"
              />
              <TouchableOpacity
                style={[
                  styles.primaryBtn,
                  { width: 'auto', marginTop: 0, paddingHorizontal: 14, justifyContent: 'center', height: 44 }
                ]}
                onPress={() => sendPriceToExitUnit(lane, exitPriceInput)}
                disabled={actionBusy}
              >
                <Text style={styles.primaryBtnText}>שלח מחיר</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Manual LPR Plate Correction (Short, Unclipped Labels) */}
        <View style={styles.fixPlateCard}>
          <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <Text style={[styles.subSectionTitle, { marginBottom: 0 }]}>✏️ תיקון מספר רכב ופתיחה</Text>
            {rawPlateClean ? (
              <TouchableOpacity
                style={{
                  backgroundColor: '#0f172a',
                  borderWidth: 1,
                  borderColor: '#475569',
                  borderRadius: 7,
                  paddingHorizontal: 8,
                  paddingVertical: 3
                }}
                onPress={() => {
                  setFixPlateText(rawPlateClean);
                  setFixPlateFirstTapClear(true);
                }}
              >
                <Text style={{ color: '#38bdf8', fontSize: 11.5, fontWeight: '800' }}>
                  זוהה: {rawPlateClean}
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>
          <Text style={{ color: '#94a3b8', fontSize: 11.5, textAlign: 'right', marginBottom: 6 }}>
            לחץ על המספר לניקוי והקלדת מספר תקין:
          </Text>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <TouchableOpacity
              style={styles.kbCheckInlineBtn}
              onPress={() => Keyboard.dismiss()}
            >
              <Text style={styles.kbCheckInlineText}>✓</Text>
            </TouchableOpacity>
            <View style={{ flex: 1, position: 'relative', justifyContent: 'center' }}>
              <TextInput
                style={[
                  styles.textInput,
                  styles.searchPlateBigInput,
                  { marginBottom: 0, height: 46, paddingHorizontal: 32 }
                ]}
                value={fixPlateText}
                onChangeText={setFixPlateText}
                onFocus={() => {
                  if (fixPlateFirstTapClear && fixPlateText) {
                    setFixPlateText('');
                    setFixPlateFirstTapClear(false);
                  }
                }}
                selectTextOnFocus={true}
                placeholder="הקלד מספר רכב"
                placeholderTextColor="#78350f"
                keyboardType="number-pad"
                returnKeyType="done"
                blurOnSubmit={true}
                onSubmitEditing={() => {
                  Keyboard.dismiss();
                  submitFixPlate();
                }}
                inputAccessoryViewID={Platform.OS === 'ios' ? KB_ACCESSORY_ID : undefined}
                textAlign="center"
              />
              {fixPlateText ? (
                <TouchableOpacity
                  onPress={() => {
                    setFixPlateText('');
                    setFixPlateFirstTapClear(false);
                  }}
                  style={{
                    position: 'absolute',
                    left: 8,
                    backgroundColor: 'rgba(15,23,42,0.18)',
                    borderRadius: 12,
                    width: 24,
                    height: 24,
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                >
                  <Text style={{ color: '#0f172a', fontWeight: '900', fontSize: 13 }}>✕</Text>
                </TouchableOpacity>
              ) : null}
            </View>
            <TouchableOpacity
              style={[
                styles.primaryBtn,
                { width: 'auto', marginTop: 0, paddingHorizontal: 16, justifyContent: 'center', height: 46 }
              ]}
              onPress={() => {
                Keyboard.dismiss();
                submitFixPlate();
              }}
              disabled={actionBusy}
            >
              <Text style={styles.primaryBtnText}>אמת ופתח</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.switchRow}>
            <Switch value={fixIgnoreSim} onValueChange={setFixIgnoreSim} />
            <Text style={{ color: '#cbd5e1', fontSize: 12 }}>
              עקיפת בדיקת דמיון תווים (אישור מנהל)
            </Text>
          </View>
          <View style={styles.switchRow}>
            <Switch value={fixForceOpen} onValueChange={setFixForceOpen} />
            <Text style={{ color: '#cbd5e1', fontSize: 12 }}>פתח מחסום מיד גם אם קיימת חסימה</Text>
          </View>
        </View>

        {!isSplitLayout && (
          <TouchableOpacity
            style={[styles.secondaryBtn, { marginTop: 14, borderColor: '#475569' }]}
            onPress={() => setSelectedUnit(null)}
          >
            <Text style={[styles.secondaryBtnText, { color: '#cbd5e1', fontWeight: '800' }]}>
              ✕ סגור וחזור לכל הנתיבים
            </Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    );
  }
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#0f172a'
  },
  authScroll: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 18
  },
  authCard: {
    width: '100%',
    backgroundColor: '#1e293b',
    borderRadius: 20,
    padding: 22,
    borderWidth: 1,
    borderColor: '#334155',
    alignItems: 'center'
  },
  authTitle: {
    color: '#f8fafc',
    fontSize: 22,
    fontWeight: '800',
    marginBottom: 6
  },
  authSubtitle: {
    color: '#94a3b8',
    fontSize: 13,
    textAlign: 'center',
    marginBottom: 18,
    lineHeight: 19
  },
  inputLabel: {
    color: '#cbd5e1',
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 6,
    textAlign: 'right'
  },
  textInput: {
    width: '100%',
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
    color: '#f8fafc',
    fontSize: 16,
    marginBottom: 12
  },
  otpTextInput: {
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: 6
  },
  kbCheckInlineBtn: {
    width: 44,
    height: 46,
    borderRadius: 12,
    backgroundColor: '#10b981',
    justifyContent: 'center',
    alignItems: 'center'
  },
  kbCheckInlineText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '900'
  },
  kbAccessoryBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderTopWidth: 1,
    borderTopColor: '#38bdf8',
    paddingHorizontal: 12,
    paddingVertical: 8
  },
  kbAccessoryActionBtn: {
    backgroundColor: '#0284c7',
    borderRadius: 9,
    paddingHorizontal: 14,
    paddingVertical: 8
  },
  kbAccessoryActionText: {
    color: '#fff',
    fontWeight: '800',
    fontSize: 13
  },
  kbAccessoryDoneBtn: {
    backgroundColor: '#10b981',
    borderRadius: 9,
    paddingHorizontal: 14,
    paddingVertical: 8
  },
  kbAccessoryDoneText: {
    color: '#fff',
    fontWeight: '800',
    fontSize: 13
  },
  primaryBtn: {
    width: '100%',
    backgroundColor: '#0284c7',
    borderRadius: 12,
    paddingVertical: 13,
    alignItems: 'center',
    marginTop: 6
  },
  primaryBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '800'
  },
  secondaryBtn: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#475569',
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
    marginTop: 10
  },
  secondaryBtnText: {
    color: '#94a3b8',
    fontSize: 13,
    fontWeight: '600'
  },
  quickOtpBtn: {
    width: '100%',
    backgroundColor: 'rgba(16,185,129,0.18)',
    borderWidth: 1,
    borderColor: '#10b981',
    borderRadius: 12,
    paddingVertical: 11,
    paddingHorizontal: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10
  },
  quickOtpBtnText: {
    color: '#6ee7b7',
    fontWeight: '800',
    fontSize: 13.5,
    textAlign: 'center',
    width: '100%'
  },
  parkingChoiceBtn: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8
  },
  parkingChoiceBtnActive: {
    borderColor: '#38bdf8',
    backgroundColor: 'rgba(56,189,248,0.12)'
  },
  parkingChoiceName: {
    color: '#f8fafc',
    fontWeight: '700',
    fontSize: 14,
    textAlign: 'right'
  },
  parkingChoiceMeta: {
    color: '#94a3b8',
    fontSize: 11,
    textAlign: 'right'
  },
  topBar: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 9,
    backgroundColor: '#1e293b',
    borderBottomWidth: 1,
    borderBottomColor: '#334155'
  },
  topBarRight: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    gap: 8,
    flex: 1
  },
  liveDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#10b981'
  },
  topBarTitle: {
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 15,
    textAlign: 'right'
  },
  topBarSub: {
    color: '#94a3b8',
    fontSize: 11,
    textAlign: 'right'
  },
  topBarActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6
  },
  switchParkingBtn: {
    backgroundColor: 'rgba(56,189,248,0.15)',
    borderWidth: 1,
    borderColor: '#38bdf8',
    borderRadius: 9,
    paddingHorizontal: 9,
    paddingVertical: 6
  },
  switchParkingBtnText: {
    color: '#38bdf8',
    fontSize: 11,
    fontWeight: '700'
  },
  iconBtn: {
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 9,
    paddingHorizontal: 9,
    paddingVertical: 6
  },
  opsContainer: {
    flex: 1
  },
  filterRow: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8
  },
  filterChip: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 99,
    paddingHorizontal: 11,
    paddingVertical: 5
  },
  filterChipActive: {
    backgroundColor: '#0284c7',
    borderColor: '#38bdf8'
  },
  filterChipText: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: '700'
  },
  lanesGrid: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingBottom: 20
  },
  laneCard: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 14,
    padding: 10,
    marginBottom: 10
  },
  laneCardSelected: {
    borderColor: '#38bdf8',
    borderWidth: 2
  },
  laneCardLocked: {
    borderColor: '#ef4444'
  },
  laneCardHeader: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8
  },
  laneName: {
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 14,
    textAlign: 'right'
  },
  laneUnitText: {
    color: '#94a3b8',
    fontSize: 11,
    textAlign: 'right'
  },
  statusBadge: {
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2
  },
  lanePlateRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    borderRadius: 9,
    paddingHorizontal: 6,
    height: 32,
    marginBottom: 8
  },
  ilPlateMini: {
    backgroundColor: '#facc15',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 2,
    borderWidth: 1.5,
    borderColor: '#1e293b',
    maxWidth: '100%'
  },
  ilPlateMiniText: {
    color: '#0f172a',
    fontWeight: '900',
    fontSize: 13,
    letterSpacing: 1,
    textAlign: 'center'
  },
  laneQuickBtns: {
    flexDirection: 'row-reverse',
    gap: 5
  },
  qBtn: {
    flex: 1,
    height: 32,
    borderRadius: 8,
    paddingHorizontal: 2,
    justifyContent: 'center',
    alignItems: 'center'
  },
  qBtnText: {
    color: '#fff',
    fontSize: 10.5,
    fontWeight: '800',
    textAlign: 'center'
  },
  splitInspectorPane: {
    flex: 1,
    borderRightWidth: 1,
    borderRightColor: '#334155',
    backgroundColor: '#162032'
  },
  inspectorHeader: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10
  },
  inspectorTitle: {
    color: '#f8fafc',
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'right'
  },
  cameraContainer: {
    width: '100%',
    height: 190,
    backgroundColor: '#020617',
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 10
  },
  cameraImage: {
    width: '100%',
    height: '100%'
  },
  cameraOverlayBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(15,23,42,0.82)',
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6
  },
  laneVehicleBox: {
    backgroundColor: '#1e293b',
    borderRadius: 11,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 10,
    alignItems: 'flex-end'
  },
  subSectionTitle: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'right',
    marginBottom: 6
  },
  cmdGrid: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 12
  },
  cmdBtn: {
    width: '32%',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    marginBottom: 6
  },
  cmdBtnText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '800'
  },
  fixPlateCard: {
    backgroundColor: '#1e293b',
    borderRadius: 13,
    padding: 11,
    borderWidth: 1,
    borderColor: '#334155'
  },
  switchRow: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    gap: 8,
    marginTop: 8
  },
  auditRow: {
    backgroundColor: '#1e293b',
    borderRadius: 9,
    padding: 8,
    marginBottom: 6,
    alignItems: 'flex-end',
    borderRightWidth: 3,
    borderRightColor: '#38bdf8'
  },
  kpiRow: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 12
  },
  kpiBox: {
    width: '48.5%',
    backgroundColor: '#1e293b',
    borderRadius: 13,
    padding: 12,
    marginBottom: 8,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155'
  },
  kpiVal: {
    color: '#f8fafc',
    fontSize: 22,
    fontWeight: '900'
  },
  kpiLbl: {
    color: '#94a3b8',
    fontSize: 11,
    marginTop: 2
  },
  sectionCard: {
    backgroundColor: '#1e293b',
    borderRadius: 14,
    padding: 13,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#334155'
  },
  sectionTitle: {
    color: '#f8fafc',
    fontSize: 15,
    fontWeight: '800',
    textAlign: 'right',
    marginBottom: 10
  },
  counterItem: {
    backgroundColor: '#0f172a',
    borderRadius: 11,
    padding: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#334155'
  },
  counterTopRow: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    marginBottom: 6
  },
  counterName: {
    color: '#f8fafc',
    fontWeight: '700',
    fontSize: 13
  },
  progressTrack: {
    height: 7,
    backgroundColor: '#1e293b',
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 6
  },
  progressFill: {
    height: '100%'
  },
  counterNumbersRow: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    marginBottom: 8
  },
  counterNumText: {
    color: '#cbd5e1',
    fontSize: 12,
    fontWeight: '700'
  },
  counterActionsRow: {
    flexDirection: 'row-reverse',
    flexWrap: 'wrap',
    gap: 6
  },
  miniActionBtn: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#475569',
    borderRadius: 7,
    paddingHorizontal: 8,
    paddingVertical: 5
  },
  miniActionText: {
    color: '#e2e8f0',
    fontSize: 11,
    fontWeight: '700'
  },
  searchBar: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 11,
    paddingHorizontal: 12,
    paddingVertical: 9,
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 14,
    textAlign: 'right',
    writingDirection: 'rtl',
    marginBottom: 10
  },
  searchBarRow: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 12,
    paddingHorizontal: 12,
    marginBottom: 10
  },
  searchBarInput: {
    flex: 1,
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 14,
    textAlign: 'right',
    writingDirection: 'rtl',
    paddingVertical: 10
  },
  companyRowCard: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#334155'
  },
  companyName: {
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 14,
    textAlign: 'right'
  },
  companyMeta: {
    color: '#94a3b8',
    fontSize: 11,
    textAlign: 'right'
  },
  companyDetailHeader: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#334155'
  },
  backBtn: {
    backgroundColor: '#334155',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7
  },
  quotaInput: {
    width: 60,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#475569',
    borderRadius: 8,
    color: '#fff',
    textAlign: 'center',
    paddingVertical: 5
  },
  quotaSaveBtn: {
    backgroundColor: '#0284c7',
    borderRadius: 8,
    paddingHorizontal: 9,
    paddingVertical: 7
  },
  presentFilterBtn: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 11,
    paddingHorizontal: 12,
    justifyContent: 'center'
  },
  subCard: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    borderRadius: 11,
    padding: 11,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#334155'
  },
  subName: {
    color: '#f8fafc',
    fontWeight: '800',
    fontSize: 13,
    textAlign: 'right'
  },
  subMeta: {
    color: '#94a3b8',
    fontSize: 11,
    textAlign: 'right',
    marginTop: 2
  },
  editSubBtn: {
    backgroundColor: 'rgba(56,189,248,0.12)',
    borderWidth: 1,
    borderColor: '#38bdf8',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6
  },
  searchPlateBigInput: {
    backgroundColor: '#fef08a',
    color: '#0f172a',
    fontWeight: '900',
    fontSize: 20,
    borderColor: '#eab308',
    borderWidth: 2
  },
  resultBoxSub: {
    backgroundColor: 'rgba(16,185,129,0.12)',
    borderWidth: 1,
    borderColor: '#10b981',
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
    alignItems: 'flex-end'
  },
  resultBoxTrans: {
    backgroundColor: 'rgba(245,158,11,0.12)',
    borderWidth: 1,
    borderColor: '#f59e0b',
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
    alignItems: 'flex-end'
  },
  resultBoxTitle: {
    color: '#6ee7b7',
    fontWeight: '800',
    fontSize: 14,
    marginBottom: 6
  },
  resultLine: {
    color: '#e2e8f0',
    fontSize: 13,
    marginBottom: 3,
    textAlign: 'right'
  },
  priceBanner: {
    width: '100%',
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    borderRadius: 10,
    padding: 10,
    marginTop: 8
  },
  priceBannerLabel: {
    color: '#fbbf24',
    fontWeight: '800',
    fontSize: 13
  },
  priceBannerValue: {
    color: '#10b981',
    fontWeight: '900',
    fontSize: 22
  },
  similarPlateBtn: {
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#38bdf8',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 5
  },
  bottomTabs: {
    flexDirection: 'row-reverse',
    backgroundColor: '#1e293b',
    borderTopWidth: 1,
    borderTopColor: '#334155',
    paddingVertical: 6
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4
  },
  tabItemActive: {
    borderTopWidth: 2,
    borderTopColor: '#38bdf8'
  },
  tabLabel: {
    color: '#94a3b8',
    fontSize: 11,
    marginTop: 2
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(2,6,23,0.78)',
    justifyContent: 'center',
    padding: 18
  },
  modalBox: {
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 18,
    borderWidth: 1,
    borderColor: '#334155'
  },
  modalTitle: {
    color: '#f8fafc',
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'right',
    marginBottom: 12
  }
});
