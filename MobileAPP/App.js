import React, { useState, useEffect, useRef } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, FlatList, Image, DeviceEventEmitter, AppState } from 'react-native';
import { SafeAreaView, SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import * as Clipboard from 'expo-clipboard';
import axios from 'axios';

// The backend URL where Flask is running
const API_URL = 'https://s-b-parking-reports.onrender.com';

// ==========================================
// 0. SHARED COMPONENTS
// ==========================================
// קומפוננטת אייקון חכמה מבוססת קוד
const LogoIcon = ({ code, size = 'large' }) => {
  const [logoUri, setLogoUri] = useState(null);

  useEffect(() => {
    const loadLogo = async () => {
      const storedUri = await AsyncStorage.getItem('app_logo_uri');
      if (storedUri) {
        setLogoUri(storedUri);
      }
    };
    loadLogo();

    // Listener to update logo globally when picked
    const subscription = DeviceEventEmitter.addListener('updateLogo', (uri) => {
      setLogoUri(uri);
    });
    return () => subscription.remove();
  }, []);

  const imageUrl = logoUri ? logoUri : `https://picsum.photos/seed/${code}/100/100`;
  const dim = size === 'small' ? 50 : 120;

  return (
    <Image
      source={{ uri: imageUrl }}
      style={[styles.logoIcon, { width: dim, height: dim, borderRadius: dim / 2 }]}
      resizeMode="cover"
    />
  );
};

// ==========================================
// 1. LOGIN SCREEN
// ==========================================
function LoginScreen({ navigation }) {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [otpMode, setOtpMode] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const checkLogin = async () => {
      try {
        const lastPhone = await AsyncStorage.getItem('last_phone_number');
        if (lastPhone) {
          setPhoneNumber(lastPhone);
        }

        const userData = await AsyncStorage.getItem('user_data');
        if (userData) {
          navigation.replace('Subscribers', { user: JSON.parse(userData) });
        }
      } catch (error) {
        console.error('Failed to read user data', error);
      }
    };
    checkLogin();
  }, []);

  // Listen for Clipboard changes or app foregrounding to catch copied WhatsApp OTP
  useEffect(() => {
    let appStateSubscription;

    if (otpMode && !loading) {
      const checkClipboardForOTP = async () => {
        try {
          const text = await Clipboard.getStringAsync();
          // Check if clipboard has exactly 6 digits
          if (text && /^\d{6}$/.test(text.trim())) {
            const digits = text.trim();
            // Don't auto-set if it's already the same, to prevent infinite loops
            if (otpCode !== digits) {
              setOtpCode(digits);
              // Option to immediately submit it:
              // handleVerifyCodeWith(digits); 
            }
          }
        } catch (e) {
          console.log("Clipboard read error: ", e);
        }
      };

      // Check right away when entering OTP mode
      checkClipboardForOTP();

      // And check whenever the app comes back from background (e.g. user went to whatsapp to copy)
      appStateSubscription = AppState.addEventListener("change", (nextAppState) => {
        if (nextAppState === "active") {
          checkClipboardForOTP();
        }
      });
    }

    return () => {
      if (appStateSubscription) {
        appStateSubscription.remove();
      }
    };
  }, [otpMode, loading, otpCode]);

  const handleSendCode = async () => {
    if (phoneNumber === '512486143') { // Secret code to open gallery
      const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (permissionResult.granted === false) {
        Alert.alert("אין הרשאות לגלריה", "אנא אשר גישה לתמונות בהגדרות אפליקציית הטלפון!");
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.5,
      });

      if (!result.canceled && result.assets && result.assets.length > 0) {
        const imageUri = result.assets[0].uri;
        await AsyncStorage.setItem('app_logo_uri', imageUri);
        DeviceEventEmitter.emit('updateLogo', imageUri);
        Alert.alert("הצלחה", "הלוגו החדש נשמר באפליקציה בצלחה!");
        setPhoneNumber('');
      } else {
        setPhoneNumber('');
      }
      return;
    }

    if (!phoneNumber || phoneNumber.length < 9) {
      Alert.alert('שגיאה', 'אנא הזן מספר נייד תקני');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${API_URL}/api/mobile/login`, {
        phone_number: phoneNumber
      }, { timeout: 10000 });

      if (response.data.success) {
        Alert.alert('הצלחה', 'קוד האימות נשלח לווטסאפ שלך!');
        setOtpMode(true);
      } else {
        Alert.alert('שגיאה', response.data.message || 'שגיאה בשליחת הקוד');
      }
    } catch (error) {
      console.error(error);
      Alert.alert('שגיאת תקשורת', 'לא ניתן להתחבר לשרת');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!otpCode || otpCode.length !== 6) {
      Alert.alert('שגיאה', 'אנא הזן קוד בן 6 ספרות');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${API_URL}/api/mobile/verify`, {
        phone_number: phoneNumber,
        otp_code: otpCode
      }, { timeout: 10000 });

      if (response.data.success) {
        await AsyncStorage.setItem('user_data', JSON.stringify(response.data.user));
        await AsyncStorage.setItem('last_phone_number', phoneNumber);
        navigation.replace('Subscribers', { user: response.data.user });
      } else {
        Alert.alert('שגיאה', response.data.message || 'הקוד שגוי');
      }
    } catch (error) {
      console.error(error);
      Alert.alert('שגיאת תקשורת', 'לא ניתן לאמת את הקוד');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={{ alignItems: 'center', marginBottom: 20 }}>
            <LogoIcon code="512486143" size="large" />
          </View>

          <View style={styles.loginCard}>
            <Text style={styles.title}>שיידט את בכמן ישראל</Text>
            <Text style={styles.subtitle}>התחברות ניידת לניהול מנויים</Text>

            {!otpMode ? (
              <>
                <Text style={styles.label}>מספר טלפון נייד להתחברות</Text>
                <TextInput
                  style={[styles.input, { textAlign: 'right' }]}
                  placeholder="0501234567"
                  keyboardType="numeric"
                  value={phoneNumber}
                  onChangeText={(text) => setPhoneNumber(text.replace(/[^0-9]/g, ''))}
                  editable={!loading}
                />

                <TouchableOpacity style={[styles.button, loading && styles.buttonDisabled]} onPress={handleSendCode} disabled={loading}>
                  {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>📲 שלח קוד בוואטסאפ</Text>}
                </TouchableOpacity>
              </>
            ) : (
              <>
                <Text style={styles.label}>קוד אימות (6 ספרות)</Text>
                <TextInput
                  style={[styles.input, { textAlign: 'center', fontSize: 24, letterSpacing: 5 }]}
                  placeholder="------"
                  keyboardType="number-pad"
                  maxLength={6}
                  value={otpCode}
                  onChangeText={setOtpCode}
                  editable={!loading}
                  textContentType="oneTimeCode"
                  autoComplete="sms-otp"
                  autoFocus={true}
                />

                <TouchableOpacity style={[styles.button, loading && styles.buttonDisabled]} onPress={handleVerifyCode} disabled={loading}>
                  {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>🔐 אמת קוד והתחבר</Text>}
                </TouchableOpacity>

                <TouchableOpacity style={styles.textButton} onPress={() => setOtpMode(false)} disabled={loading}>
                  <Text style={styles.textButtonText}>חזור להחלפת מספר טלפון</Text>
                </TouchableOpacity>
              </>
            )}
          </View>

          <View style={styles.footerContainer}>
            <Text style={styles.footerText}>גרסה 3.1.1</Text>
            <Text style={styles.footerText}>By Dror Prince ®</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ==========================================
// 2. DASHBOARD SCREEN
// ==========================================
function DashboardScreen({ route, navigation }) {
  const user = route.params?.user;

  const handleLogout = async () => {
    try {
      await AsyncStorage.removeItem('user_data');
      navigation.replace('Login');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <LogoIcon code="512486143" size="small" />
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={styles.dashboardTitle}>שלום, {user?.username}</Text>
            <Text style={styles.dashboardSubtitle}>{user?.parking_name} ({user?.project_number})</Text>
          </View>
        </View>
      </View>

      <View style={styles.modulesContainer}>
        <TouchableOpacity
          style={styles.moduleButton}
          onPress={() => navigation.navigate('Subscribers', { user })}
        >
          <Text style={styles.moduleEmoji}>👥</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.moduleText}>ניהול מנויים</Text>
            <Text style={styles.moduleDesc}>הוספה, עריכה וחיפוש מנויים בחניון</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.moduleButton, { opacity: 0.5 }]} disabled={true}>
          <Text style={styles.moduleEmoji}>📷</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.moduleText}>סורק רכבים (בקרוב)</Text>
            <Text style={styles.moduleDesc}>סריקת לוחית רישוי ופתיחת שערים</Text>
          </View>
        </TouchableOpacity>
      </View>

      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Text style={styles.logoutText}>🚪 התנתק מהמערכת</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

// ==========================================
// 3. SUBSCRIBERS SCREEN
// ==========================================
function SubscribersScreen({ route, navigation }) {
  const user = route.params?.user;
  const [loading, setLoading] = useState(true);
  const [subscribers, setSubscribers] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [parkingName, setParkingName] = useState('');

  useEffect(() => {
    fetchSubscribers();
  }, []);

  const fetchSubscribers = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API_URL}/api/mobile/get-subscribers`, {
        project_number: user.project_number,
        user_id: user.user_id,
        company_list: user.company_list,
      }, { timeout: 60000 });

      if (response.data.success) {
        // פענוח הנתונים כי הם עלולים לחזור כ-JSON רגיל מקונברטור או כמערך
        let subsData = response.data.data;
        if (subsData && subsData.consumers && subsData.consumers.consumer) {
          subsData = subsData.consumers.consumer;
        }
        if (!Array.isArray(subsData)) {
          subsData = subsData ? [subsData] : [];
        }
        setSubscribers(subsData);
        if (response.data.parking_name) {
          setParkingName(response.data.parking_name);
        }
      } else {
        Alert.alert('שגיאה', response.data.message || 'שגיאה במשיכת מנויים');
      }
    } catch (error) {
      console.error(error);
      Alert.alert('שגיאת תקשורת', 'לא ניתן לקרוא נתונים משרת החניון');
    } finally {
      setLoading(false);
    }
  };

  // סינון מנויים לפי חיפוש
  const filteredSubs = subscribers.filter(sub => {
    const fullTerm = `${sub.firstName || ''} ${sub.lastName || ''} ${sub.contractName || ''} ${sub.lpn1 || ''}`.toLowerCase();
    return fullTerm.includes(searchQuery.toLowerCase());
  });

  const renderSubscriberItem = ({ item, index }) => {
    const fname = typeof item.firstName === 'string' ? item.firstName : (item.firstName?.['#text'] || '');
    const lname = typeof item.lastName === 'string' ? item.lastName : (item.lastName?.['#text'] || '');
    const name = `${fname} ${lname}`.trim() || 'ללא שם';

    let licensePlate = 'אין רכב מוגדר';
    if (item.lpn1) {
      licensePlate = typeof item.lpn1 === 'string' ? item.lpn1 : (item.lpn1.plate || 'אין רכב מוגדר');
    } else if (item.vehicle1) {
      licensePlate = typeof item.vehicle1 === 'string' ? item.vehicle1 : (item.vehicle1.plate || 'אין רכב מוגדר');
    }

    let licensePlate2 = '-';
    if (item.lpn2) {
      licensePlate2 = typeof item.lpn2 === 'string' ? item.lpn2 : (item.lpn2.plate || '-');
    }

    let licensePlate3 = '-';
    if (item.lpn3) {
      licensePlate3 = typeof item.lpn3 === 'string' ? item.lpn3 : (item.lpn3.plate || '-');
    }

    const subNum = item.subscriberNum || index;
    const isExpanded = expandedId === subNum;

    return (
      <TouchableOpacity
        style={[styles.subscriberItem, isExpanded && { backgroundColor: '#f0f4f8' }]}
        onPress={() => setExpandedId(isExpanded ? null : subNum)}
      >
        <View style={styles.subTopRow}>
          <Text style={styles.subName}>{name}</Text>
          <View style={styles.subCarBadge}>
            <Text style={styles.subCarText}>{licensePlate}</Text>
          </View>
        </View>

        {isExpanded && (
          <View style={styles.subExpandedDetails}>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>מספר חברה:</Text>
              <Text style={styles.subDetailValue}>{item.contractId || item.companyNum || '-'}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>תחילת תוקף:</Text>
              <Text style={styles.subDetailValue}>{item.validFrom ? item.validFrom.split('T')[0] : '-'}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>תוקף עד:</Text>
              <Text style={styles.subDetailValue}>{item.validUntil ? item.validUntil.split('T')[0] : '-'}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>רכב 2:</Text>
              <Text style={styles.subDetailValue}>{licensePlate2}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>רכב 3:</Text>
              <Text style={styles.subDetailValue}>{licensePlate3}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>פרופיל:</Text>
              <Text style={styles.subDetailValue}>{item.profileName || item.profile || item.extCardProfile || '-'}</Text>
            </View>
            <View style={styles.subDetailRow}>
              <Text style={styles.subDetailLabel}>נוכח בחניון:</Text>
              <Text style={styles.subDetailValue}>{item.presence ? 'כן' : 'לא'}</Text>
            </View>

            <View style={{ flexDirection: 'row-reverse', justifyContent: 'space-around', marginVertical: 10 }}>
              <TouchableOpacity
                style={styles.actionButton}
                onPress={() => navigation.navigate('EditSubscriber', { subscriber: item, user: user })}
              >
                <Text style={styles.actionButtonText}>✏️ ערוך מנוי</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  // מציאת שם החברה לראש העמוד
  const getSubCorpName = (sub) => typeof sub.contractName === 'string' ? sub.contractName : (sub.companyName || '');
  const getSubCorpId = (sub) => sub.contractId || sub.contractid || sub.companyNum || '';

  const displayCompanyName = parkingName || 'חניון ' + (user?.project_number || '');
  const displayCompanyId = subscribers.length > 0 ? (getSubCorpId(subscribers[0]) || user.company_list || 'כללי') : (user.company_list || 'כללי');

  const handleLogout = async () => {
    try {
      await AsyncStorage.removeItem('user_data');
      navigation.replace('Login');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.headerAlt}>
        <TouchableOpacity onPress={handleLogout} style={styles.backButton}>
          <Text style={{ fontSize: 24 }}>🚪</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={{ alignItems: 'flex-end', marginLeft: 15 }}>
            <Text style={styles.dashboardTitle}>{displayCompanyName}</Text>
            {displayCompanyId ? <Text style={styles.dashboardSubtitle}>חברה: {displayCompanyId} ({subscribers.length} מנויים)</Text> : null}
          </View>
          <LogoIcon code="512486143" size="small" />
        </View>
      </View>

      <View style={styles.searchContainer}>
        <TextInput
          style={[styles.searchInput, { textAlign: 'right' }]}
          placeholder="חיפוש..."
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#2c3e50" />
          <Text style={{ marginTop: 10, color: '#7f8c8d' }}>מתחבר לחניון ומושך נתונים...</Text>
        </View>
      ) : (
        <FlatList
          data={filteredSubs}
          keyExtractor={(item, index) => item.id ? item.id.toString() : index.toString()}
          renderItem={renderSubscriberItem}
          contentContainerStyle={{ padding: 15, paddingBottom: 50 }}
          ListEmptyComponent={<Text style={styles.emptyText}>לא נמצאו מנויים</Text>}
        />
      )}

      <TouchableOpacity
        style={styles.floatingButton}
        onPress={() => navigation.navigate('EditSubscriber', { subscriber: {}, user: user, isNew: true })}
      >
        <Text style={styles.floatingButtonText}>+</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

// ==========================================
// 4. EDIT SUBSCRIBER SCREEN
// ==========================================
function EditSubscriberScreen({ route, navigation }) {
  const { subscriber, user, isNew } = route.params;

  const defaultCompany = user?.company_list ? user.company_list.split(',')[0] : '';
  const [cId, setCId] = useState(subscriber.contractId || subscriber.companyNum || subscriber.contractid || defaultCompany);
  const [sId, setSId] = useState(subscriber.id || subscriber.subscriberNum || '');

  const [fname, setFname] = useState(typeof subscriber.firstName === 'string' ? subscriber.firstName : (subscriber.firstName?.['#text'] || ''));
  const [lname, setLname] = useState(typeof subscriber.lastName === 'string' ? subscriber.lastName : (subscriber.lastName?.['#text'] || ''));

  const extractLpn = (lpnObj) => typeof lpnObj === 'string' ? lpnObj : (lpnObj?.plate || '');
  const [lpn1, setLpn1] = useState(extractLpn(subscriber.lpn1) || extractLpn(subscriber.vehicle1) || '');
  const [lpn2, setLpn2] = useState(extractLpn(subscriber.lpn2) || '');
  const [lpn3, setLpn3] = useState(extractLpn(subscriber.lpn3) || '');

  const [validFrom, setValidFrom] = useState(subscriber.validFrom ? subscriber.validFrom.split('T')[0] : '');
  const [validUntil, setValidUntil] = useState(subscriber.validUntil ? subscriber.validUntil.split('T')[0] : '');

  const [profileId, setProfileId] = useState(subscriber.profileId || subscriber.profile || subscriber.extCardProfile || '1');
  const [tagNum, setTagNum] = useState(subscriber.tagNum || '');

  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!cId) {
      Alert.alert('שגיאה', 'מזהה חברה חסר, לא ניתן לשמור');
      return;
    }
    if (!isNew && !sId) {
      Alert.alert('שגיאה', 'מזהה מנוי חסר, לא ניתן לעדכן');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        consumer: {
          id: sId,
          contractid: cId,
          xValidFrom: validFrom ? validFrom + 'T00:00:00+03:00' : undefined,
          xValidUntil: validUntil ? validUntil + 'T23:59:59+03:00' : undefined
        },
        person: { firstName: fname, surname: lname },
        identification: {
          ptcptType: '2',
          cardno: tagNum,
          cardclass: '1',
          identificationType: '54',
          validFrom: validFrom ? validFrom + 'T00:00:00+03:00' : undefined,
          validUntil: validUntil ? validUntil + 'T23:59:59+03:00' : undefined,
          usageProfile: {
            id: profileId || '1'
          }
        }
      };

      if (lpn1) payload.lpn1 = lpn1.replace(/-/g, '');
      if (lpn2) payload.lpn2 = lpn2.replace(/-/g, '');
      if (lpn3) payload.lpn3 = lpn3.replace(/-/g, '');

      const endpoint = isNew ? `contracts/${cId}/consumers` : `consumers/${cId},${sId}/detail`;
      const method = isNew ? 'POST' : 'PUT';

      const response = await axios.post(`${API_URL}/api/company-manager/proxy`, {
        endpoint: endpoint,
        method: method,
        parking_id: user.project_number,
        _internal_session: { user_email: user.user_id },
        payload: payload
      }, { timeout: 60000 });

      if (response.data.success) {
        Alert.alert('הצלחה', isNew ? 'המנוי נוסף בהצלחה' : 'המנוי עודכן בהצלחה', [
          { text: 'אישור', onPress: () => navigation.goBack() }
        ]);
      } else {
        Alert.alert('שגיאה', response.data.message || 'שגיאה בשמירת מנוי');
      }
    } catch (error) {
      console.error(error);
      Alert.alert('שגיאת תקשורת', 'לא ניתן לעדכן את המנוי כרגע');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.headerAlt}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Text style={{ fontSize: 24 }}>🔙</Text>
        </TouchableOpacity>
        <Text style={styles.dashboardTitle}>{isNew ? 'הוספת מנוי חדש' : 'עריכת מנוי'}</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20 }}>
        <View style={styles.editCard}>

          {isNew && (
            <>
              <Text style={styles.label}>מספר חברה</Text>
              <TextInput style={styles.input} value={cId} onChangeText={setCId} textAlign="right" />

              <Text style={styles.label}>מספר מנוי (השאר ריק למספר אוטומטי)</Text>
              <TextInput style={styles.input} value={sId} onChangeText={setSId} textAlign="right" />
            </>
          )}

          <Text style={styles.label}>שם פרטי</Text>
          <TextInput style={styles.input} value={fname} onChangeText={setFname} textAlign="right" />

          <Text style={styles.label}>שם משפחה</Text>
          <TextInput style={styles.input} value={lname} onChangeText={setLname} textAlign="right" />

          <Text style={styles.label}>מספר כרטיס (Tag)</Text>
          <TextInput style={styles.input} value={tagNum} onChangeText={setTagNum} textAlign="right" />

          <Text style={styles.label}>מזהה פרופיל (לדוגמה: 1 לפרופיל סטנדרטי)</Text>
          <TextInput style={styles.input} value={profileId} onChangeText={setProfileId} textAlign="right" />

          <Text style={styles.label}>רכב 1</Text>
          <TextInput style={styles.input} value={lpn1} onChangeText={setLpn1} textAlign="right" />

          <Text style={styles.label}>רכב 2</Text>
          <TextInput style={styles.input} value={lpn2} onChangeText={setLpn2} textAlign="right" />

          <Text style={styles.label}>רכב 3</Text>
          <TextInput style={styles.input} value={lpn3} onChangeText={setLpn3} textAlign="right" />

          <Text style={styles.label}>תחילת תוקף (YYYY-MM-DD)</Text>
          <TextInput style={styles.input} value={validFrom} onChangeText={setValidFrom} textAlign="right" />

          <Text style={styles.label}>תוקף עד (YYYY-MM-DD)</Text>
          <TextInput style={styles.input} value={validUntil} onChangeText={setValidUntil} textAlign="right" />

          <TouchableOpacity
            style={[styles.button, saving && styles.buttonDisabled]}
            onPress={handleSave}
            disabled={saving}
          >
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>שמור שינויים</Text>}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ==========================================
// NAVIGATION SETUP
// ==========================================
const Stack = createStackNavigator();

export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <Stack.Navigator screenOptions={{ headerShown: false, cardStyle: { backgroundColor: '#f5f7fa' } }}>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Subscribers" component={SubscribersScreen} />
          <Stack.Screen name="EditSubscriber" component={EditSubscriberScreen} />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

// ==========================================
// STYLES
// ==========================================
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f7fa',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  loginCard: {
    backgroundColor: '#fff',
    padding: 30,
    borderRadius: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.1,
    shadowRadius: 15,
    elevation: 5,
    alignItems: 'center'
  },
  editCard: {
    backgroundColor: '#fff',
    padding: 20,
    borderRadius: 15,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 3,
  },
  logoIcon: {
    width: 80,
    height: 80,
    marginBottom: 15,
    borderRadius: 15
  },
  title: {
    fontSize: 23,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 5,
    textAlign: 'center'
  },
  subtitle: {
    fontSize: 16,
    color: '#7f8c8d',
    marginBottom: 30,
  },
  label: {
    alignSelf: 'flex-end',
    marginBottom: 8,
    fontSize: 14,
    color: '#34495e',
    fontWeight: '600'
  },
  input: {
    width: '100%',
    height: 50,
    backgroundColor: '#ecf0f1',
    borderRadius: 10,
    paddingHorizontal: 15,
    fontSize: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#bdc3c7',
  },
  button: {
    width: '100%',
    backgroundColor: '#27ae60',
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 10,
  },
  buttonDisabled: {
    backgroundColor: '#95a5a6',
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  textButton: {
    marginTop: 20,
  },
  textButtonText: {
    color: '#3498db',
    fontSize: 14,
  },
  header: {
    padding: 25,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderColor: '#eee',
    alignItems: 'flex-end'
  },
  headerAlt: {
    paddingTop: Platform.OS === 'android' ? 40 : 20,
    paddingHorizontal: 20,
    paddingBottom: 15,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderColor: '#eee',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between'
  },
  backButton: {
    padding: 5,
  },
  dashboardTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#2c3e50',
  },
  dashboardSubtitle: {
    fontSize: 16,
    color: '#7f8c8d',
    marginTop: 5,
  },
  modulesContainer: {
    flex: 1,
    padding: 20,
  },
  moduleButton: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e1e8ed',
    flexDirection: 'row-reverse',
    alignItems: 'center',
    padding: 20,
    borderRadius: 15,
    marginBottom: 15,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 5,
    elevation: 2,
  },
  moduleEmoji: {
    fontSize: 32,
    marginLeft: 15,
  },
  moduleText: {
    fontSize: 18,
    color: '#2c3e50',
    fontWeight: 'bold',
    textAlign: 'right'
  },
  moduleDesc: {
    color: '#7f8c8d',
    fontSize: 13,
    textAlign: 'right',
    marginTop: 3
  },
  logoutButton: {
    backgroundColor: '#ff7675',
    padding: 18,
    alignItems: 'center',
    margin: 20,
    borderRadius: 12
  },
  logoutText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center'
  },
  searchContainer: {
    padding: 15,
    backgroundColor: '#fff'
  },
  searchInput: {
    backgroundColor: '#f1f2f6',
    height: 45,
    borderRadius: 8,
    paddingHorizontal: 15,
    fontSize: 15
  },
  subscriberItem: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 15,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
    borderRightWidth: 4,
    borderColor: '#3498db'
  },
  subDetails: {
    flex: 1,
    alignItems: 'flex-end',
    marginRight: 10
  },
  subName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 4
  },
  subCompany: {
    fontSize: 13,
    color: '#7f8c8d',
    marginBottom: 2
  },
  subDate: {
    fontSize: 12,
    color: '#95a5a6'
  },
  subCarBadge: {
    backgroundColor: '#f1f2f6',
    borderWidth: 1,
    borderColor: '#bdc3c7',
    borderRadius: 6,
    paddingVertical: 5,
    paddingHorizontal: 10,
    minWidth: 100,
    maxWidth: 150,
    alignItems: 'center'
  },
  subCarText: {
    fontWeight: 'bold',
    fontSize: 14,
    color: '#f39c12'
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 50,
    color: '#95a5a6',
    fontSize: 16
  },
  floatingButton: {
    position: 'absolute',
    bottom: 30,
    left: 30,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#3498db',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 8,
  },
  floatingButtonText: {
    color: '#fff',
    fontSize: 30,
    fontWeight: '200',
    marginTop: -2
  },
  footerContainer: {
    marginTop: 30,
    alignItems: 'center',
    justifyContent: 'center'
  },
  footerText: {
    color: '#95a5a6',
    fontSize: 14,
    marginBottom: 5,
    fontWeight: '500'
  },
  subTopRow: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    alignItems: 'center',
    width: '100%'
  },
  subExpandedDetails: {
    marginTop: 15,
    paddingTop: 15,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    width: '100%',
  },
  subDetailRow: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    marginBottom: 5,
  },
  subDetailLabel: {
    color: '#7f8c8d',
    fontSize: 14,
    fontWeight: 'bold'
  },
  subDetailValue: {
    color: '#34495e',
    fontSize: 14,
  },
  actionButton: {
    backgroundColor: '#fff',
    borderColor: '#3498db',
    borderWidth: 1,
    paddingVertical: 8,
    paddingHorizontal: 15,
    borderRadius: 8,
  },
  actionButtonText: {
    color: '#3498db',
    fontWeight: 'bold',
  }
});
